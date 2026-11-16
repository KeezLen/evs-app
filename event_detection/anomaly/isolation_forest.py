"""Isolation Forest detector for unusual household consumption."""

from collections.abc import Sequence
from datetime import datetime
from datetime import timedelta
import math

import numpy as np
from sklearn.ensemble import IsolationForest

from event_detection.schemas import Event, SeriesPoint
from .base import AnomalyDetector


class IsolationForestAnomalyDetector(AnomalyDetector):
    """Detect unusual electricity and gas observations per household series."""

    name = "isolation_forest"
    # Provisional chronological split. Revisit this with validation results if
    # a different household history length improves detector performance.
    training_ratio = 0.7
    # A conservative initial rate is appropriate while real event labels are
    # unavailable. This remains tunable after comparing false positives.
    contamination = 0.01

    def __init__(
        self,
        contamination: float | None = None,
        minimum_samples: int = 30,
        training_ratio: float | None = None,
        random_state: int = 42,
        n_estimators: int = 200,
    ) -> None:
        self.contamination = contamination if contamination is not None else self.contamination
        self.minimum_samples = minimum_samples
        self.training_ratio = training_ratio if training_ratio is not None else self.training_ratio
        self.random_state = random_state
        self.n_estimators = n_estimators

    def detect(
        self,
        series: Sequence[SeriesPoint],
        detection_start: datetime | None = None,
    ) -> list[Event]:
        """Fit per-signal models and return anomalous valid observations."""
        events: list[Event] = []
        for signal_name in ("electricity", "gas"):
            signal_events = self._detect_signal(series, signal_name, detection_start)
            events.extend(signal_events)
        return sorted(events, key=lambda event: event.start)

    def _detect_signal(
        self,
        series: Sequence[SeriesPoint],
        signal_name: str,
        detection_start: datetime | None = None,
    ) -> list[Event]:
        value_attribute = "electricity_kwh" if signal_name == "electricity" else "gas_m3"
        points = [
            point
            for point in series
            if point.quality_flag == "ok" and getattr(point, value_attribute) is not None
        ]
        training_count = int(len(points) * self.training_ratio)
        if detection_start is not None:
            requested_split = next(
                (index for index, point in enumerate(points) if point.timestamp >= detection_start),
                len(points),
            )
            if requested_split >= self.minimum_samples and requested_split < len(points):
                training_count = requested_split
        if training_count < self.minimum_samples or training_count >= len(points):
            return []

        training_points = points[:training_count]
        detection_points = points[training_count:]
        training_features = self._features(training_points, value_attribute)
        detection_features = self._features(detection_points, value_attribute)
        model = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            random_state=self.random_state,
        )
        model.fit(training_features)
        predictions = model.predict(detection_features)
        decisions = model.decision_function(detection_features)
        baseline = float(np.median([getattr(point, value_attribute) for point in training_points]))
        events = [
            self._event(
                point,
                signal_name,
                float(getattr(point, value_attribute)),
                baseline,
                float(decision),
                self._confidence(decisions, index),
            )
            for index, (point, prediction, decision) in enumerate(
                zip(detection_points, predictions, decisions)
            )
            if prediction == -1
        ]
        return self._aggregate_events(events)

    @staticmethod
    def _aggregate_events(events: list[Event]) -> list[Event]:
        """Merge consecutive anomalous intervals into readable event windows."""
        if not events:
            return []
        aggregated: list[Event] = []
        current = [events[0]]
        for event in events[1:]:
            previous = current[-1]
            if event.type == previous.type and event.start == previous.end:
                current.append(event)
            else:
                aggregated.append(IsolationForestAnomalyDetector._merge_events(current))
                current = [event]
        aggregated.append(IsolationForestAnomalyDetector._merge_events(current))
        return aggregated

    @staticmethod
    def _merge_events(events: list[Event]) -> Event:
        """Build one event window from adjacent interval-level findings."""
        first = events[0]
        last = events[-1]
        observed_values = [float(event.details["observed"]) for event in events]
        return first.model_copy(update={
            "id": f"{first.type}:{first.start.isoformat()}",
            "end": last.end,
            "magnitude": round(max(event.magnitude for event in events), 3),
            "confidence": round(max(event.confidence for event in events), 3),
            "details": {
                **first.details,
                "observed": round(max(observed_values), 3),
                "interval_count": len(events),
                "duration_minutes": int((last.end - first.start).total_seconds() / 60),
            },
        })

    @staticmethod
    def _features(points: Sequence[SeriesPoint], value_attribute: str) -> np.ndarray:
        """Build time-aware rows while imputing only optional context features."""
        raw_rows = []
        for point in points:
            value = getattr(point, value_attribute)
            assert value is not None
            angle_hour = 2 * math.pi * point.timestamp.hour / 24
            angle_weekday = 2 * math.pi * point.timestamp.weekday() / 7
            raw_rows.append([
                value,
                math.sin(angle_hour),
                math.cos(angle_hour),
                math.sin(angle_weekday),
                math.cos(angle_weekday),
                point.temp_mean_c,
                point.hdd18,
            ])
        rows = np.asarray(raw_rows, dtype=float)
        for column in range(rows.shape[1]):
            values = rows[:, column]
            finite = np.isfinite(values)
            if finite.any():
                values[~finite] = np.median(values[finite])
            else:
                values[:] = 0.0
        return rows

    def _event(
        self,
        point: SeriesPoint,
        signal_name: str,
        value: float,
        baseline: float,
        decision: float,
        confidence: float,
    ) -> Event:
        event_type = f"unusual_{signal_name}"
        return Event(
            id=f"{event_type}:{point.timestamp.isoformat()}",
            type=event_type,
            start=point.timestamp,
            end=point.timestamp + timedelta(minutes=point.interval_minutes),
            magnitude=round(abs(value - baseline), 3),
            confidence=round(confidence, 3),
            method=self.name,
            details={
                "observed": value,
                "median": round(baseline, 3),
                "anomaly_score": round(-decision, 6),
                "quality_flag": point.quality_flag,
            },
        )

    @staticmethod
    def _confidence(decisions: np.ndarray, index: int) -> float:
        """Convert the relative Isolation Forest score into a 0-1 confidence."""
        highest = float(np.max(decisions))
        lowest = float(np.min(decisions))
        if highest == lowest:
            return 1.0
        return max(0.0, min(1.0, (highest - float(decisions[index])) / (highest - lowest)))