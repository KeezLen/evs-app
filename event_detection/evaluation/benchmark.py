"""Deterministic held-out benchmark preparation and scoring utilities."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
import math
import random
from statistics import median
from time import perf_counter

from event_detection.anomaly.isolation_forest import IsolationForestAnomalyDetector
from event_detection.anomaly.rnn import RNNForecastDetector
from event_detection.data import get_series
from event_detection.nilm.rules import RuleBasedDetector
from event_detection.schemas import Event, SeriesPoint
from .matching import summarize_benchmark_events

BENCHMARK_PATTERNS = ("spikes", "sustained_high", "low_use", "weather_gas")


@dataclass(frozen=True)
class BenchmarkPartitions:
    training: list[SeriesPoint]
    calibration: list[SeriesPoint]
    test: list[SeriesPoint]


@dataclass(frozen=True)
class InjectionSpec:
    pattern: str
    signal: str
    direction: str
    strength: float
    duration_hours: int


def chronological_split(points: Sequence[SeriesPoint]) -> BenchmarkPartitions:
    """Split ordered data into 70% train, 10% calibration, and 20% test."""
    ordered = sorted(points, key=lambda point: point.timestamp)
    training_end = int(len(ordered) * 0.7)
    calibration_end = int(len(ordered) * 0.8)
    if training_end == 0 or calibration_end <= training_end or calibration_end >= len(ordered):
        raise ValueError("Benchmark requires enough points for chronological train/calibration/test splits")
    return BenchmarkPartitions(
        training=ordered[:training_end],
        calibration=ordered[training_end:calibration_end],
        test=ordered[calibration_end:],
    )


def injection_specs(
    patterns: Sequence[str],
    has_gas: bool,
    strengths: Sequence[float] | None = None,
) -> list[InjectionSpec]:
    """Expand selected pattern families into fixed, reviewable test cases."""
    unknown = set(patterns) - set(BENCHMARK_PATTERNS)
    if unknown:
        raise ValueError(f"Unknown benchmark patterns: {sorted(unknown)}")
    allowed_strengths = {0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 2.0}
    selected_strengths = allowed_strengths if strengths is None else set(strengths)
    if not selected_strengths or not selected_strengths <= allowed_strengths:
        raise ValueError("Benchmark strengths must be selected from 0.3, 0.4, 0.5, 0.6, 0.8, 1, 2")
    signals = ["electricity"] + (["gas"] if has_gas else [])
    specs: list[InjectionSpec] = []
    if "spikes" in patterns:
        for signal in signals:
            specs.extend(
                InjectionSpec("spike", signal, "high", strength, 1)
                for strength in (0.5, 1.0, 2.0)
                if strength in selected_strengths
            )
    if "low_use" in patterns:
        for signal in signals:
            specs.extend(
                InjectionSpec("low_use", signal, "low", strength, 6)
                for strength in (0.5, 0.8)
                if strength in selected_strengths
            )
    if "sustained_high" in patterns:
        for signal in signals:
            specs.extend(
                InjectionSpec("sustained_high", signal, "high", strength, duration)
                for strength in (0.3, 0.6)
                if strength in selected_strengths
                for duration in (6, 24)
            )
    if "weather_gas" in patterns and has_gas:
        specs.extend(
            InjectionSpec("weather_gas", "gas", "high", strength, 6)
            for strength in (0.4, 0.6)
            if strength in selected_strengths
        )
    return specs


def generate_benchmark_cases(
    partitions: BenchmarkPartitions,
    patterns: Sequence[str],
    seed: int,
    weather_gas_enabled: bool,
    strengths: Sequence[float] | None = None,
) -> tuple[list[SeriesPoint], list[Event]]:
    """Return a perturbed test copy and labeled injections, never mutating source points."""
    has_gas = any(point.gas_m3 is not None for point in partitions.training + partitions.test)
    selected_patterns = [
        pattern for pattern in patterns
        if pattern != "weather_gas" or (weather_gas_enabled and has_gas)
    ]
    if not selected_patterns:
        return list(partitions.test), []
    specs = injection_specs(selected_patterns, has_gas, strengths)
    if not specs:
        raise ValueError("Selected event patterns and strengths do not produce any injections")

    interval_minutes = partitions.test[0].interval_minutes
    test = list(partitions.test)
    training = partitions.training
    specs.sort(key=lambda spec: (spec.signal, spec.pattern, spec.duration_hours, spec.strength))
    occupied: set[int] = set()
    truth: list[Event] = []
    randomizer = random.Random(seed)
    candidate_cursor = 0

    for spec_index, spec in enumerate(specs):
        attribute = "electricity_kwh" if spec.signal == "electricity" else "gas_m3"
        duration_steps = max(1, math.ceil(spec.duration_hours * 60 / interval_minutes))
        candidate_indices = [
            start
            for start in range(candidate_cursor, len(test) - duration_steps + 1)
            if all(
                test[index].quality_flag == "ok"
                and getattr(test[index], attribute) is not None
                and (index not in occupied)
                for index in range(start, start + duration_steps)
            )
        ]
        if spec.pattern == "weather_gas":
            hdds = [point.hdd18 for point in training if point.hdd18 is not None]
            if not hdds:
                continue
            cold_cutoff = sorted(hdds)[int(0.75 * (len(hdds) - 1))]
            candidate_indices = [
                start for start in candidate_indices
                if all(test[index].hdd18 is not None and test[index].hdd18 >= cold_cutoff
                       for index in range(start, start + duration_steps))
            ]
        if not candidate_indices:
            candidate_indices = [
                start
                for start in range(0, len(test) - duration_steps + 1)
                if all(
                    test[index].quality_flag == "ok"
                    and getattr(test[index], attribute) is not None
                    and index not in occupied
                    for index in range(start, start + duration_steps)
                )
            ]
        if not candidate_indices:
            continue

        # Spread perturbations over the test period, while keeping each pattern reproducible.
        desired = min(len(candidate_indices) - 1, int((spec_index + 1) * len(candidate_indices) / (len(specs) + 1)))
        candidate_start = candidate_indices[(desired + randomizer.randrange(min(3, len(candidate_indices)))) % len(candidate_indices)]
        baseline = _context_baseline(training, attribute, test[candidate_start], spec.pattern == "weather_gas")
        if baseline <= 0:
            continue

        changed: list[SeriesPoint] = []
        for index in range(candidate_start, candidate_start + duration_steps):
            point = test[index]
            original = float(getattr(point, attribute))
            if spec.direction == "low":
                injected = max(0.0, baseline * (1.0 - spec.strength))
            elif spec.pattern == "spike":
                injected = max(original, baseline) * (1.0 + spec.strength)
            else:
                injected = max(original, baseline) * (1.0 + spec.strength)
            changed_point = point.model_copy(update={attribute: injected})
            changed.append(changed_point)
            occupied.add(index)
        test[candidate_start:candidate_start + duration_steps] = changed
        start_time = changed[0].timestamp
        end_time = changed[-1].timestamp + timedelta(minutes=interval_minutes)
        truth.append(Event(
            id=f"synthetic:{spec.pattern}:{spec.signal}:{spec.strength}:{start_time.isoformat()}",
            type=f"unusual_{spec.signal}",
            start=start_time,
            end=end_time,
            magnitude=round(max(abs(float(getattr(point, attribute)) - baseline) for point in changed), 4),
            confidence=1.0,
            method="synthetic_ground_truth",
            details={
                "pattern": spec.pattern,
                "signal": spec.signal,
                "direction": spec.direction,
                "strength": spec.strength,
                "duration_hours": duration_steps * interval_minutes / 60,
                "requested_duration_hours": spec.duration_hours,
            },
        ))
        candidate_cursor = min(len(test) - duration_steps, candidate_start + duration_steps + max(1, duration_steps // 2))

    return test, truth


def _context_baseline(
    training: Sequence[SeriesPoint],
    attribute: str,
    target: SeriesPoint,
    weather_conditioned: bool,
) -> float:
    values = [
        (point, float(getattr(point, attribute)))
        for point in training
        if point.quality_flag == "ok" and getattr(point, attribute) is not None
    ]
    if not values:
        return 0.0
    if weather_conditioned and target.hdd18 is not None:
        cold_values = [
            value for point, value in values
            if point.hdd18 is not None and point.hdd18 >= target.hdd18 * 0.75
        ]
        if cold_values:
            values_only = cold_values
        else:
            values_only = [value for _, value in values]
    elif target.interval_minutes < 1440:
        same_hour = [
            value for point, value in values
            if point.timestamp.hour == target.timestamp.hour
        ]
        values_only = same_hour or [value for _, value in values]
    else:
        values_only = [value for _, value in values]
    positive = [value for value in values_only if value > 0]
    return median(positive or values_only)


def run_household_benchmark(
    dataset: str,
    household: str,
    patterns: Sequence[str],
    seed: int,
    weather_gas_enabled: bool,
    lookback_days: int = 1,
    strengths: Sequence[float] | None = None,
) -> dict[str, object]:
    """Run normal and injected held-out data through all applicable detectors."""
    points = get_series(dataset, household)
    partitions = chronological_split(points)
    injected_test, truth = generate_benchmark_cases(
        partitions,
        patterns,
        seed,
        weather_gas_enabled,
        strengths,
    )
    resolution = points[0].interval_minutes
    duration_hours = (
        (partitions.test[-1].timestamp - partitions.test[0].timestamp).total_seconds() / 3600
        + resolution / 60
    )
    if duration_hours <= 0:
        raise ValueError(f"Not enough test duration for {household}")

    applicable: list[tuple[str, object]] = []
    if resolution == 1440:
        applicable.append(("rules", RuleBasedDetector()))
    applicable.append(("isolation_forest", IsolationForestAnomalyDetector()))
    if resolution in {15, 60}:
        applicable.append(("rnn", RNNForecastDetector()))

    method_results = []
    tolerance = max(resolution, 15)
    for method, detector in applicable:
        started = perf_counter()
        if method == "rules":
            normal_events = detector.detect(partitions.test, reference_series=partitions.training)
            injected_events = detector.detect(injected_test, reference_series=partitions.training)
        elif method == "isolation_forest":
            normal_events = detector.detect_benchmark(
                partitions.training, partitions.calibration, partitions.test
            )
            injected_events = detector.detect_benchmark(
                partitions.training, partitions.calibration, injected_test
            )
        else:
            normal_events = detector.detect_benchmark(
                partitions.training,
                partitions.calibration,
                partitions.test,
                lookback_days=lookback_days,
            )
            injected_events = detector.detect_benchmark(
                partitions.training,
                partitions.calibration,
                injected_test,
                lookback_days=lookback_days,
            )
        runtime_ms = round((perf_counter() - started) * 1000, 2)
        injected_scores = summarize_benchmark_events(
            injected_events,
            truth,
            duration_hours,
            tolerance,
        )
        normal_scores = summarize_benchmark_events(
            normal_events,
            [],
            duration_hours,
            tolerance,
        )
        normal_weeks = max(duration_hours / 168, 1 / 168)
        for normal_class in normal_scores["classes"]:
            normal_class["alerts_per_household_week"] = round(
                normal_class["detected"] / normal_weeks,
                4,
            )
        method_results.append({
            "method": method,
            "applicable": True,
            "runtime_ms": runtime_ms,
            "normal_event_count": len(normal_events),
            "normal_false_alarms_per_household_week": normal_scores["false_alarms_per_household_week"],
            "normal_scores": normal_scores,
            "injected_event_count": len(injected_events),
            "scores": injected_scores,
            "detected_events": injected_events,
        })

    if resolution == 1440:
        method_results.append({"method": "rnn", "applicable": False, "reason": "RNN benchmark supports hourly and 15-minute data."})
    return {
        "dataset": dataset,
        "household": household,
        "resolution_minutes": resolution,
        "point_counts": {
            "training": len(partitions.training),
            "calibration": len(partitions.calibration),
            "test": len(partitions.test),
        },
        "date_ranges": {
            "training_start": partitions.training[0].timestamp,
            "training_end": partitions.training[-1].timestamp,
            "calibration_start": partitions.calibration[0].timestamp,
            "calibration_end": partitions.calibration[-1].timestamp,
            "test_start": partitions.test[0].timestamp,
            "test_end": partitions.test[-1].timestamp,
        },
        "seed": seed,
        "weather_gas_enabled": weather_gas_enabled and any(event.details.get("pattern") == "weather_gas" for event in truth),
        "ground_truth": truth,
        "methods": method_results,
    }