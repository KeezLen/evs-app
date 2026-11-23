"""Deterministic held-out benchmark preparation and scoring utilities."""

from collections import Counter
from collections.abc import Callable, Sequence
from bisect import bisect_left
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


def rolling_weekly_splits(points: Sequence[SeriesPoint], training_weeks: int) -> list[BenchmarkPartitions]:
    """Create full, non-overlapping test weeks with preceding training and calibration."""
    if training_weeks not in {2, 4, 8}:
        raise ValueError("Training weeks must be 2, 4, or 8")
    ordered = sorted(points, key=lambda point: point.timestamp)
    if not ordered:
        raise ValueError("No readings available for rolling benchmark")
    resolution = ordered[0].interval_minutes
    if any(point.interval_minutes != resolution for point in ordered):
        raise ValueError("Rolling benchmark requires a consistent resolution")
    timestamps = [point.timestamp for point in ordered]
    start = timestamps[0]
    end = timestamps[-1] + timedelta(minutes=resolution)
    week = timedelta(weeks=1)
    splits = []
    while start + (training_weeks + 2) * week <= end:
        calibration_start = start + training_weeks * week
        test_start = calibration_start + week
        test_end = test_start + week
        training_index = bisect_left(timestamps, start)
        calibration_index = bisect_left(timestamps, calibration_start)
        test_index = bisect_left(timestamps, test_start)
        end_index = bisect_left(timestamps, test_end)
        partitions = BenchmarkPartitions(
            training=ordered[training_index:calibration_index],
            calibration=ordered[calibration_index:test_index],
            test=ordered[test_index:end_index],
        )
        if not partitions.training or not partitions.calibration or not partitions.test:
            raise ValueError(f"Rolling window starting {start.isoformat()} has an empty partition")
        splits.append(partitions)
        start += week
    if not splits:
        raise ValueError(f"Rolling benchmark requires at least {training_weeks + 2} weeks of readings")
    return splits


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
    protocol: str = "corrected_v2",
    skipped: list[dict] | None = None,
) -> tuple[list[SeriesPoint], list[Event]]:
    """Return a perturbed test copy and labeled injections, never mutating source points."""
    if protocol not in {"legacy_v1", "corrected_v2"}:
        raise ValueError(f"Unknown benchmark protocol: {protocol}")
    has_gas = any(point.gas_m3 is not None for point in partitions.training + partitions.test)
    selected_patterns = [
        pattern for pattern in patterns
        if pattern != "weather_gas" or (weather_gas_enabled and has_gas)
    ]
    if skipped is not None and "weather_gas" in patterns and "weather_gas" not in selected_patterns:
        skipped.append({"pattern": "weather_gas", "signal": "gas", "reason": "weather audit disabled" if has_gas else "no gas data"})
    if skipped is not None and not has_gas:
        skipped.extend({"pattern": pattern, "signal": "gas", "reason": "no gas data"} for pattern in selected_patterns)
    if not selected_patterns:
        return list(partitions.test), []
    specs = injection_specs(selected_patterns, has_gas, strengths)
    if not specs:
        raise ValueError("Selected event patterns and strengths do not produce any injections")
    if skipped is not None:
        spec_patterns = {"spikes" if spec.pattern == "spike" else spec.pattern for spec in specs}
        skipped.extend({"pattern": pattern, "signal": "all", "reason": "no compatible selected strength"} for pattern in selected_patterns if pattern not in spec_patterns)

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
        def eligible(start: int) -> bool:
            window = test[start:start + duration_steps]
            return all(
                point.quality_flag == "ok"
                and getattr(point, attribute) is not None
                and start + offset not in occupied
                and (protocol == "legacy_v1" or spec.direction != "low" or getattr(point, attribute) > 0)
                and (protocol == "legacy_v1" or (point.interval_minutes == interval_minutes
                     and point.timestamp == window[0].timestamp + timedelta(minutes=interval_minutes * offset)))
                for offset, point in enumerate(window)
            )

        candidate_indices = [start for start in range(candidate_cursor, len(test) - duration_steps + 1) if eligible(start)]
        cold_cutoff = None
        if spec.pattern == "weather_gas":
            hdds = [point.hdd18 for point in training if point.hdd18 is not None and (protocol == "legacy_v1" or point.quality_flag == "ok")]
            if not hdds:
                if skipped is not None:
                    skipped.append({"pattern": spec.pattern, "signal": spec.signal, "strength": spec.strength, "reason": "no training weather"})
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
                if eligible(start)
                and (protocol == "legacy_v1" or cold_cutoff is None or all(
                    test[index].hdd18 is not None and test[index].hdd18 >= cold_cutoff
                    for index in range(start, start + duration_steps)
                ))
            ]
        if not candidate_indices:
            if skipped is not None:
                skipped.append({"pattern": spec.pattern, "signal": spec.signal, "strength": spec.strength, "reason": "no eligible contiguous test window"})
            continue

        # Spread perturbations over the test period, while keeping each pattern reproducible.
        desired = min(len(candidate_indices) - 1, int((spec_index + 1) * len(candidate_indices) / (len(specs) + 1)))
        candidate_start = candidate_indices[(desired + randomizer.randrange(min(3, len(candidate_indices)))) % len(candidate_indices)]
        baseline = _context_baseline(training, attribute, test[candidate_start], spec.pattern == "weather_gas")
        if baseline <= 0:
            if skipped is not None:
                skipped.append({"pattern": spec.pattern, "signal": spec.signal, "strength": spec.strength, "reason": "no positive training baseline"})
            continue

        changed: list[SeriesPoint] = []
        originals: list[float] = []
        changes: list[float] = []
        for index in range(candidate_start, candidate_start + duration_steps):
            point = test[index]
            original = float(getattr(point, attribute))
            if spec.direction == "low":
                injected = max(0.0, (baseline if protocol == "legacy_v1" else original) * (1.0 - spec.strength))
            elif spec.pattern == "spike":
                injected = max(original, baseline) * (1.0 + spec.strength)
            else:
                injected = max(original, baseline) * (1.0 + spec.strength)
            changed_point = point.model_copy(update={attribute: injected})
            changed.append(changed_point)
            originals.append(original)
            changes.append(injected - original)
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
                "original_values": originals,
                "injected_values": [float(getattr(point, attribute)) for point in changed],
                "realized_deltas": changes,
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


def detector_support_diagnostics(
    partitions: BenchmarkPartitions,
    lookback_days: int,
) -> dict[str, dict[str, dict[str, int | str]]]:
    """Report data support and minimum-window eligibility by detector and signal."""
    diagnostics: dict[str, dict[str, dict[str, int | str]]] = {
        "rules": {},
        "isolation_forest": {},
        "rnn": {},
    }
    resolution = partitions.training[0].interval_minutes
    isolation_forest = IsolationForestAnomalyDetector()
    for signal in ("electricity", "gas"):
        attribute = "electricity_kwh" if signal == "electricity" else "gas_m3"

        def valid(points: Sequence[SeriesPoint]) -> list[SeriesPoint]:
            return [point for point in points if point.quality_flag == "ok" and getattr(point, attribute) is not None]

        training_points = valid(partitions.training)
        calibration_points = valid(partitions.calibration)
        test_points = valid(partitions.test)
        if resolution != 1440:
            rules_status = "unsupported_resolution"
        elif signal == "gas":
            gas_baseline_points = [point for point in training_points if point.hdd18 is not None]
            rules_status = (
                "sufficient_support"
                if len(gas_baseline_points) >= RuleBasedDetector.minimum_gas_history
                else "insufficient_gas_weather_history"
            )
        else:
            rules_status = "sufficient_support" if training_points else "no_valid_training_data"
        diagnostics["rules"][signal] = {
            "status": rules_status,
            "training_points": len(training_points),
            "calibration_points": len(calibration_points),
            "test_points": len(test_points),
            "baseline_points": len(gas_baseline_points) if signal == "gas" and resolution == 1440 else len(training_points),
        }

        iforest_status = "sufficient_support"
        if len(training_points) < isolation_forest.minimum_samples:
            iforest_status = "insufficient_training_points"
        elif len(calibration_points) < 10:
            iforest_status = "insufficient_calibration_points"
        elif not test_points:
            iforest_status = "no_valid_test_points"
        diagnostics["isolation_forest"][signal] = {
            "status": iforest_status,
            "training_points": len(training_points),
            "calibration_points": len(calibration_points),
            "test_points": len(test_points),
        }

        rnn: dict[str, int | str] = {
            "status": "sufficient_support",
            "training_points": len(training_points),
            "calibration_points": len(calibration_points),
            "test_points": len(test_points),
            "lookback_days": lookback_days,
            "training_windows": 0,
            "calibration_windows": 0,
            "test_windows": 0,
        }
        if resolution not in {15, 60}:
            rnn["status"] = "unsupported_resolution"
        elif not training_points or not calibration_points:
            rnn["status"] = "missing_training_or_calibration_data"
        else:
            horizon_steps = 60 // resolution
            lookback_steps = lookback_days * 1440 // resolution
            training_segments = RNNForecastDetector._contiguous_segments(training_points, attribute)
            training_windows = sum(
                max(0, len(segment) - lookback_steps - horizon_steps + 1)
                for segment in training_segments
            )
            rnn["training_windows"] = training_windows
            if training_windows < RNNForecastDetector.minimum_training_windows:
                rnn["status"] = "insufficient_training_windows"
            elif not test_points:
                rnn["status"] = "no_valid_test_points"
            else:
                test_start = test_points[0].timestamp
                full_history = sorted(training_points + calibration_points + test_points, key=lambda point: point.timestamp)
                full_segments = RNNForecastDetector._contiguous_segments(full_history, attribute)
                test_windows = 0
                for segment in full_segments:
                    first_target = max(
                        lookback_steps,
                        next((index for index, point in enumerate(segment) if point.timestamp >= test_start), len(segment)),
                    )
                    test_windows += len(range(first_target, len(segment) - horizon_steps + 1, horizon_steps))
                rnn["test_windows"] = test_windows
                calibration_history = sorted(training_points + calibration_points, key=lambda point: point.timestamp)
                calibration_segments = RNNForecastDetector._contiguous_segments(calibration_history, attribute)
                calibration_start = calibration_points[0].timestamp
                calibration_end = calibration_points[-1].timestamp
                possible_calibration_windows = sum(
                    1
                    for segment in calibration_segments
                    for start in range(lookback_steps, len(segment) - horizon_steps + 1)
                    if segment[start].timestamp >= calibration_start
                    and segment[start + horizon_steps - 1].timestamp <= calibration_end
                )
                stride = max(1, math.ceil(possible_calibration_windows / RNNForecastDetector.max_training_windows))
                usable_calibration_windows = (
                    math.ceil(possible_calibration_windows / stride)
                    if possible_calibration_windows else 0
                )
                rnn["calibration_windows"] = usable_calibration_windows
                if usable_calibration_windows < 8:
                    rnn["status"] = "insufficient_calibration_windows"
                elif not test_windows:
                    rnn["status"] = "no_test_forecast_windows"
        diagnostics["rnn"][signal] = rnn
    return diagnostics


def random_budget_events(
    test: Sequence[SeriesPoint],
    budget_events: Sequence[Event],
    seed: int,
) -> list[Event]:
    """Place seeded random alerts in valid test windows at a reference alert budget."""
    if not test:
        return []
    interval_minutes = test[0].interval_minutes
    randomizer = random.Random(seed)
    generated: list[Event] = []
    segments_by_attribute: dict[str, list[tuple[int, int]]] = {}

    def valid_segments(attribute: str) -> list[tuple[int, int]]:
        if attribute in segments_by_attribute:
            return segments_by_attribute[attribute]
        segments: list[tuple[int, int]] = []
        segment_start: int | None = None
        for index, point in enumerate(test):
            valid = point.quality_flag == "ok" and getattr(point, attribute) is not None
            contiguous = (
                segment_start is not None
                and point.interval_minutes == interval_minutes
                and point.timestamp == test[index - 1].timestamp + timedelta(minutes=interval_minutes)
            )
            if not valid or (segment_start is not None and not contiguous):
                if segment_start is not None:
                    segments.append((segment_start, index))
                    segment_start = None
            if valid and segment_start is None:
                segment_start = index
        if segment_start is not None:
            segments.append((segment_start, len(test)))
        segments_by_attribute[attribute] = segments
        return segments

    for event_index, budget_event in enumerate(budget_events):
        signal = "gas" if "gas" in budget_event.type else "electricity"
        attribute = "gas_m3" if signal == "gas" else "electricity_kwh"
        duration_steps = max(1, math.ceil((budget_event.end - budget_event.start).total_seconds() / (interval_minutes * 60)))
        segments = valid_segments(attribute)
        candidate_count = sum(max(0, end - start - duration_steps + 1) for start, end in segments)
        if not candidate_count:
            continue
        candidate_offset = randomizer.randrange(candidate_count)
        start_index = 0
        for segment_start, segment_end in segments:
            segment_candidates = max(0, segment_end - segment_start - duration_steps + 1)
            if candidate_offset < segment_candidates:
                start_index = segment_start + candidate_offset
                break
            candidate_offset -= segment_candidates
        start_point = test[start_index]
        end_point = test[start_index + duration_steps - 1]
        generated.append(budget_event.model_copy(update={
            "id": f"random:{seed}:{event_index}:{start_point.timestamp.isoformat()}",
            "start": start_point.timestamp,
            "end": end_point.timestamp + timedelta(minutes=interval_minutes),
            "method": "random_budget",
            "details": {**budget_event.details, "random_control_seed": seed},
        }))
    return generated


def run_household_benchmark(
    dataset: str,
    household: str,
    patterns: Sequence[str],
    seed: int,
    weather_gas_enabled: bool,
    lookback_days: int = 1,
    strengths: Sequence[float] | None = None,
    protocol: str = "corrected_v2",
) -> dict[str, object]:
    """Run normal and injected held-out data through all applicable detectors."""
    points = get_series(dataset, household)
    partitions = chronological_split(points)
    return _run_partition_benchmark(
        dataset, household, partitions, patterns, seed, weather_gas_enabled,
        lookback_days, strengths, protocol,
    )


def _run_partition_benchmark(
    dataset: str,
    household: str,
    partitions: BenchmarkPartitions,
    patterns: Sequence[str],
    seed: int,
    weather_gas_enabled: bool,
    lookback_days: int,
    strengths: Sequence[float] | None,
    protocol: str,
) -> dict[str, object]:
    diagnostics = detector_support_diagnostics(partitions, lookback_days)
    skipped: list[dict] = []
    injected_test, truth = generate_benchmark_cases(
        partitions,
        patterns,
        seed,
        weather_gas_enabled,
        strengths,
        protocol,
        skipped,
    )
    resolution = partitions.training[0].interval_minutes
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
    detector_budgets: list[tuple[str, list[Event], dict]] = []
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
            protocol,
        )
        normal_scores = summarize_benchmark_events(
            normal_events,
            [],
            duration_hours,
            tolerance,
            protocol,
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
            "diagnostics": diagnostics[method],
            "runtime_ms": runtime_ms,
            "normal_event_count": len(normal_events),
            "normal_false_alarms_per_household_week": normal_scores["false_alarms_per_household_week"],
            "normal_scores": normal_scores,
            "injected_event_count": len(injected_events),
            "scores": injected_scores,
            "detected_events": injected_events,
        })
        detector_budgets.append((method, normal_events, normal_scores))

    no_alert_scores = summarize_benchmark_events([], truth, duration_hours, tolerance, protocol)
    method_results.append({
        "method": "no_alert",
        "applicable": True,
        "baseline": True,
        "runtime_ms": 0,
        "normal_event_count": 0,
        "normal_false_alarms_per_household_week": 0.0,
        "normal_scores": {"classes": [], "false_alarms_per_household_week": 0.0},
        "injected_event_count": 0,
        "scores": no_alert_scores,
        "detected_events": [],
    })
    for index, (method, budget_events, normal_scores) in enumerate(detector_budgets):
        random_events = random_budget_events(partitions.test, budget_events, seed + index)
        random_scores = summarize_benchmark_events(random_events, truth, duration_hours, tolerance, protocol)
        method_results.append({
            "method": f"random_budget_{method}",
            "baseline": True,
            "baseline_for": method,
            "applicable": True,
            "runtime_ms": 0,
            "normal_event_count": len(budget_events),
            "random_alert_budget": len(budget_events),
            "random_alerts_generated": len(random_events),
            "random_seed": seed + index,
            "normal_false_alarms_per_household_week": normal_scores["false_alarms_per_household_week"],
            "normal_scores": normal_scores,
            "injected_event_count": len(random_events),
            "scores": random_scores,
            "detected_events": random_events,
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
        "protocol": protocol,
        "patterns": list(patterns),
        "strengths": list(strengths) if strengths is not None else None,
        "lookback_days": lookback_days,
        "skipped_injections": skipped,
        "detector_support": diagnostics,
        "weather_gas_enabled": weather_gas_enabled and any(event.details.get("pattern") == "weather_gas" for event in truth),
        "ground_truth": truth,
        "methods": method_results,
    }


def run_household_rolling_benchmark(
    dataset: str,
    household: str,
    patterns: Sequence[str],
    seed: int,
    weather_gas_enabled: bool,
    lookback_days: int,
    strengths: Sequence[float] | None,
    protocol: str,
    training_weeks: int,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, object]]:
    partitions = rolling_weekly_splits(get_series(dataset, household), training_weeks)
    results = []
    if on_progress is not None:
        on_progress(0, len(partitions))
    for index, split in enumerate(partitions):
        result = _run_partition_benchmark(
            dataset, household, split, patterns, seed, weather_gas_enabled,
            lookback_days, strengths, protocol,
        )
        result.update({"training_weeks": training_weeks, "week_index": index + 1})
        results.append(result)
        if on_progress is not None:
            on_progress(index + 1, len(partitions))
    return results