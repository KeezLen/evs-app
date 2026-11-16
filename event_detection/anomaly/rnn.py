"""Cached household LSTM forecasts for short-horizon consumption anomalies."""

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import math
from threading import RLock

import numpy as np
import torch
from torch import nn

from event_detection.schemas import Event, SeriesPoint
from .base import AnomalyDetector


class _LSTMForecaster(nn.Module):
    def __init__(self, feature_count: int, horizon_steps: int) -> None:
        super().__init__()
        self.lstm = nn.LSTM(feature_count, 16, batch_first=True)
        self.output = nn.Linear(16, horizon_steps)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        sequence, _ = self.lstm(inputs)
        return self.output(sequence[:, -1, :])


@dataclass
class _TrainedModel:
    model: _LSTMForecaster
    center: float
    scale: float
    positive_threshold: float
    negative_threshold: float
    horizon_steps: int


class RNNForecastDetector(AnomalyDetector):
    """Forecast electricity/gas per household and flag unusual residuals."""

    name = "rnn"
    minimum_training_windows = 40
    validation_fraction = 0.2
    validation_quantile = 0.99
    epochs = 8
    batch_size = 128
    max_training_windows = 4096
    cache_limit = 16
    _model_cache: OrderedDict[str, _TrainedModel] = OrderedDict()
    _cache_lock = RLock()

    def detect(
        self,
        series: Sequence[SeriesPoint],
        detection_start: datetime | None = None,
        lookback_days: int = 1,
    ) -> list[Event]:
        """Train/cache each available signal and score only the detection window."""
        if lookback_days not in {1, 7}:
            raise ValueError("RNN lookback_days must be 1 or 7")
        points = sorted(series, key=lambda point: point.timestamp)
        if not points or points[0].interval_minutes not in {15, 60}:
            return []

        events: list[Event] = []
        for signal_name in ("electricity", "gas"):
            events.extend(self._detect_signal(points, signal_name, detection_start, lookback_days))
        return sorted(events, key=lambda event: event.start)

    def detect_benchmark(
        self,
        training: Sequence[SeriesPoint],
        calibration: Sequence[SeriesPoint],
        test: Sequence[SeriesPoint],
        lookback_days: int = 1,
    ) -> list[Event]:
        """Fit on the training partition, calibrate on calibration, score test."""
        if lookback_days not in {1, 7}:
            raise ValueError("RNN lookback_days must be 1 or 7")
        events: list[Event] = []
        for signal_name in ("electricity", "gas"):
            events.extend(self._detect_benchmark_signal(
                training, calibration, test, signal_name, lookback_days
            ))
        return sorted(events, key=lambda event: event.start)

    def _detect_benchmark_signal(
        self,
        training: Sequence[SeriesPoint],
        calibration: Sequence[SeriesPoint],
        test: Sequence[SeriesPoint],
        signal_name: str,
        lookback_days: int,
    ) -> list[Event]:
        value_attribute = "electricity_kwh" if signal_name == "electricity" else "gas_m3"

        def valid(points: Sequence[SeriesPoint]) -> list[SeriesPoint]:
            return [point for point in points if point.quality_flag == "ok" and getattr(point, value_attribute) is not None]

        training_points = valid(training)
        calibration_points = valid(calibration)
        test_points = valid(test)
        if not training_points or not calibration_points or not test_points:
            return []
        interval_minutes = training_points[0].interval_minutes
        if interval_minutes not in {15, 60} or any(point.interval_minutes != interval_minutes for point in training_points + calibration_points + test_points):
            return []
        horizon_steps = 60 // interval_minutes
        lookback_steps = lookback_days * 1440 // interval_minutes
        bundle = self._get_or_train(
            training_points,
            value_attribute,
            signal_name,
            lookback_steps,
            horizon_steps,
            calibration_points=calibration_points,
        )
        if bundle is None:
            return []

        full_history = sorted(training_points + calibration_points + test_points, key=lambda point: point.timestamp)
        detection_start = test_points[0].timestamp
        events: list[Event] = []
        for segment in self._contiguous_segments(full_history, value_attribute):
            target_start = max(
                lookback_steps,
                next((index for index, point in enumerate(segment) if point.timestamp >= detection_start), len(segment)),
            )
            for target_start in range(target_start, len(segment) - horizon_steps + 1, horizon_steps):
                context = segment[target_start - lookback_steps:target_start]
                inputs = np.asarray([
                    self._features(point, value_attribute, bundle.center, bundle.scale)
                    for point in context
                ], dtype=np.float32)
                with torch.inference_mode():
                    predictions = bundle.model(torch.from_numpy(inputs).unsqueeze(0)).cpu().numpy()[0]
                for offset, predicted_normalized in enumerate(predictions):
                    point = segment[target_start + offset]
                    observed = float(getattr(point, value_attribute))
                    predicted = float(predicted_normalized * bundle.scale + bundle.center)
                    residual = observed - predicted
                    threshold = bundle.positive_threshold if residual >= 0 else bundle.negative_threshold
                    if abs(residual) > threshold:
                        events.append(self._event(
                            point, signal_name, observed, predicted, residual, threshold,
                            lookback_days, horizon_steps * interval_minutes,
                        ))
        return self._aggregate_events(events)

    def _detect_signal(
        self,
        series: Sequence[SeriesPoint],
        signal_name: str,
        detection_start: datetime | None,
        lookback_days: int,
    ) -> list[Event]:
        value_attribute = "electricity_kwh" if signal_name == "electricity" else "gas_m3"
        points = [
            point for point in series
            if point.quality_flag == "ok" and getattr(point, value_attribute) is not None
        ]
        if not points:
            return []

        interval_minutes = points[0].interval_minutes
        if interval_minutes not in {15, 60}:
            return []
        horizon_steps = 60 // interval_minutes
        lookback_steps = lookback_days * 1440 // interval_minutes
        requested_training_count = (
            next((index for index, point in enumerate(points) if point.timestamp >= detection_start), len(points))
            if detection_start is not None
            else 0
        )

        minimum_training_points = lookback_steps + horizon_steps + self.minimum_training_windows - 1
        if detection_start is not None and requested_training_count >= minimum_training_points:
            training_count = requested_training_count
            effective_detection_start = detection_start
        else:
            training_count = int(len(points) * 0.7)
            if training_count < lookback_steps + self.minimum_training_windows:
                return []
            fallback_start = points[training_count].timestamp
            effective_detection_start = max(detection_start, fallback_start) if detection_start else fallback_start

        training_points = points[:training_count]
        bundle = self._get_or_train(
            training_points,
            value_attribute,
            signal_name,
            lookback_steps,
            horizon_steps,
        )
        if bundle is None:
            return []

        events: list[Event] = []
        for segment in self._contiguous_segments(points, value_attribute):
            first_target = max(
                lookback_steps,
                next((index for index, point in enumerate(segment) if point.timestamp >= effective_detection_start), len(segment)),
            )
            for target_start in range(first_target, len(segment) - horizon_steps + 1, horizon_steps):
                context = segment[target_start - lookback_steps:target_start]
                inputs = np.asarray([self._features(point, value_attribute, bundle.center, bundle.scale) for point in context], dtype=np.float32)
                with torch.inference_mode():
                    prediction = bundle.model(torch.from_numpy(inputs).unsqueeze(0)).cpu().numpy()[0]
                for offset, predicted_normalized in enumerate(prediction):
                    point = segment[target_start + offset]
                    observed = float(getattr(point, value_attribute))
                    predicted = float(predicted_normalized * bundle.scale + bundle.center)
                    residual = observed - predicted
                    threshold = bundle.positive_threshold if residual >= 0 else bundle.negative_threshold
                    if abs(residual) > threshold:
                        events.append(self._event(
                            point,
                            signal_name,
                            observed,
                            predicted,
                            residual,
                            threshold,
                            lookback_days,
                            horizon_steps * interval_minutes,
                        ))
        return self._aggregate_events(events)

    def _get_or_train(
        self,
        training_points: Sequence[SeriesPoint],
        value_attribute: str,
        signal_name: str,
        lookback_steps: int,
        horizon_steps: int,
        calibration_points: Sequence[SeriesPoint] | None = None,
    ) -> _TrainedModel | None:
        segments = self._contiguous_segments(training_points, value_attribute)
        values = np.asarray([float(getattr(point, value_attribute)) for point in training_points], dtype=np.float64)
        center = float(np.median(values))
        mad_scale = float(np.median(np.abs(values - center)) * 1.4826)
        scale = max(mad_scale, float(np.std(values)), 1e-6)
        features, targets = self._windows(segments, value_attribute, lookback_steps, horizon_steps, center, scale)
        if len(features) < self.minimum_training_windows:
            return None

        if calibration_points is not None:
            calibration_valid = [
                point for point in calibration_points
                if point.quality_flag == "ok" and getattr(point, value_attribute) is not None
            ]
            if not calibration_valid:
                return None
            calibration_history = self._contiguous_segments(
                sorted(list(training_points) + calibration_valid, key=lambda point: point.timestamp),
                value_attribute,
            )
            calibration_features, calibration_targets = self._windows(
                calibration_history,
                value_attribute,
                lookback_steps,
                horizon_steps,
                center,
                scale,
                target_time_start=calibration_valid[0].timestamp,
                target_time_end=calibration_valid[-1].timestamp,
            )
            train_features = features
            train_targets = targets
            if len(calibration_features) < 8:
                return None
        else:
            validation_count = max(8, int(len(features) * self.validation_fraction))
            training_end = len(features) - validation_count
            if training_end < 16:
                return None
            train_features = features[:training_end]
            train_targets = targets[:training_end]
            calibration_features = features[training_end:]
            calibration_targets = targets[training_end:]

        key_hash = hashlib.sha256()
        key_hash.update(f"{signal_name}:{lookback_steps}:{horizon_steps}:{center:.10g}:{scale:.10g}".encode())
        key_hash.update(train_features.tobytes())
        key_hash.update(train_targets.tobytes())
        key_hash.update(calibration_features.tobytes())
        key_hash.update(calibration_targets.tobytes())
        key = key_hash.hexdigest()
        with self._cache_lock:
            cached = self._model_cache.get(key)
            if cached is not None:
                self._model_cache.move_to_end(key)
                return cached

        if len(train_features) < 16:
            return None
        torch.manual_seed(42)
        model = _LSTMForecaster(features.shape[-1], horizon_steps)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
        loss_function = nn.HuberLoss()
        train_inputs = torch.from_numpy(train_features)
        torch_targets = torch.from_numpy(train_targets)
        for _ in range(self.epochs):
            model.train()
            for offset in range(0, len(train_features), self.batch_size):
                batch_inputs = train_inputs[offset:offset + self.batch_size]
                batch_targets = torch_targets[offset:offset + self.batch_size]
                optimizer.zero_grad()
                loss = loss_function(model(batch_inputs), batch_targets)
                loss.backward()
                optimizer.step()

        model.eval()
        with torch.inference_mode():
            validation_predictions = model(torch.from_numpy(calibration_features)).numpy()
        residuals = calibration_targets - validation_predictions
        # Median +/- 3 MAD is a robust, compact alternative, but assumes a
        # roughly symmetric residual tail and can miss skewed forecast errors.
        # The empirical 99th percentile adapts to the held-out tail, provided
        # there are enough validation windows; both remain tunable choices.
        absolute_threshold = float(np.quantile(np.abs(residuals), self.validation_quantile))
        positive = residuals[residuals > 0]
        negative = -residuals[residuals < 0]
        positive_threshold = float(np.quantile(positive, self.validation_quantile)) if len(positive) else absolute_threshold
        negative_threshold = float(np.quantile(negative, self.validation_quantile)) if len(negative) else absolute_threshold
        bundle = _TrainedModel(
            model=model,
            center=center,
            scale=scale,
            positive_threshold=max(positive_threshold * scale, 1e-6),
            negative_threshold=max(negative_threshold * scale, 1e-6),
            horizon_steps=horizon_steps,
        )
        with self._cache_lock:
            self._model_cache[key] = bundle
            self._model_cache.move_to_end(key)
            while len(self._model_cache) > self.cache_limit:
                self._model_cache.popitem(last=False)
        return bundle

    @classmethod
    def _windows(
        cls,
        segments: Sequence[Sequence[SeriesPoint]],
        value_attribute: str,
        lookback_steps: int,
        horizon_steps: int,
        center: float,
        scale: float,
        target_time_start: datetime | None = None,
        target_time_end: datetime | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        feature_windows: list[list[list[float]]] = []
        target_windows: list[list[float]] = []
        possible_windows = 0
        for segment in segments:
            for start in range(lookback_steps, len(segment) - horizon_steps + 1):
                target = segment[start:start + horizon_steps]
                if target_time_start is not None and target[0].timestamp < target_time_start:
                    continue
                if target_time_end is not None and target[-1].timestamp > target_time_end:
                    continue
                possible_windows += 1
        stride = max(1, math.ceil(possible_windows / RNNForecastDetector.max_training_windows))
        window_index = 0
        for segment in segments:
            for window_start in range(lookback_steps, len(segment) - horizon_steps + 1):
                target = segment[window_start:window_start + horizon_steps]
                if target_time_start is not None and target[0].timestamp < target_time_start:
                    continue
                if target_time_end is not None and target[-1].timestamp > target_time_end:
                    continue
                include_window = window_index % stride == 0
                window_index += 1
                if not include_window:
                    continue
                context = segment[window_start - lookback_steps:window_start]
                feature_windows.append([
                    cls._features(point, value_attribute, center, scale) for point in context
                ])
                target_windows.append([
                    (float(getattr(point, value_attribute)) - center) / scale for point in target
                ])
        return np.asarray(feature_windows, dtype=np.float32), np.asarray(target_windows, dtype=np.float32)

    @staticmethod
    def _contiguous_segments(
        points: Sequence[SeriesPoint],
        value_attribute: str,
    ) -> list[list[SeriesPoint]]:
        segments: list[list[SeriesPoint]] = []
        current: list[SeriesPoint] = []
        for point in points:
            value = getattr(point, value_attribute)
            is_valid = point.quality_flag == "ok" and value is not None
            is_contiguous = (
                current
                and point.interval_minutes == current[-1].interval_minutes
                and point.timestamp - current[-1].timestamp == timedelta(minutes=point.interval_minutes)
            )
            if not is_valid or (current and not is_contiguous):
                if current:
                    segments.append(current)
                current = []
            if is_valid:
                current.append(point)
        if current:
            segments.append(current)
        return segments

    @staticmethod
    def _features(
        point: SeriesPoint,
        value_attribute: str,
        center: float,
        scale: float,
    ) -> list[float]:
        value = float(getattr(point, value_attribute))
        hour_angle = 2 * math.pi * (point.timestamp.hour + point.timestamp.minute / 60) / 24
        weekday_angle = 2 * math.pi * point.timestamp.weekday() / 7
        return [
            (value - center) / scale,
            math.sin(hour_angle),
            math.cos(hour_angle),
            math.sin(weekday_angle),
            math.cos(weekday_angle),
            (point.temp_mean_c or 0.0) / 30,
            (point.hdd18 or 0.0) / 30,
        ]

    @classmethod
    def _aggregate_events(cls, events: list[Event]) -> list[Event]:
        if not events:
            return []
        aggregated: list[Event] = []
        current = [events[0]]
        for event in events[1:]:
            if (
                event.type == current[-1].type
                and event.details.get("direction") == current[-1].details.get("direction")
                and event.start == current[-1].end
            ):
                current.append(event)
            else:
                aggregated.append(cls._merge_events(current))
                current = [event]
        aggregated.append(cls._merge_events(current))
        return aggregated

    @staticmethod
    def _merge_events(events: list[Event]) -> Event:
        first = events[0]
        last = events[-1]
        return first.model_copy(update={
            "id": f"{first.type}:{first.start.isoformat()}",
            "end": last.end,
            "magnitude": round(max(event.magnitude for event in events), 3),
            "confidence": round(max(event.confidence for event in events), 3),
            "details": {
                **first.details,
                "interval_count": len(events),
                "duration_minutes": int((last.end - first.start).total_seconds() / 60),
            },
        })

    def _event(
        self,
        point: SeriesPoint,
        signal_name: str,
        observed: float,
        predicted: float,
        residual: float,
        threshold: float,
        lookback_days: int,
        horizon_minutes: int,
    ) -> Event:
        event_type = f"unusual_{signal_name}"
        direction = "high" if residual > 0 else "low"
        return Event(
            id=f"{event_type}:{point.timestamp.isoformat()}",
            type=event_type,
            start=point.timestamp,
            end=point.timestamp + timedelta(minutes=point.interval_minutes),
            magnitude=round(abs(residual), 3),
            confidence=min(1.0, round(abs(residual) / max(abs(residual) + threshold, 1e-9), 3)),
            method=self.name,
            details={
                "observed": observed,
                "predicted": round(predicted, 4),
                "residual": round(residual, 4),
                "threshold": round(threshold, 4),
                "direction": direction,
                "lookback_days": lookback_days,
                "forecast_horizon_minutes": horizon_minutes,
            },
        )