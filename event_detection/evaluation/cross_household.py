"""Cold-start comparison of pooled and household-specific Isolation Forests."""

from bisect import bisect_left
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
import random
from time import perf_counter

import numpy as np
from sklearn.ensemble import IsolationForest

from event_detection.anomaly.isolation_forest import IsolationForestAnomalyDetector
from event_detection.data import get_series_many
from event_detection.schemas import Event, SeriesPoint
from .benchmark import (
    BenchmarkPartitions, chronological_split, generate_benchmark_cases,
    random_budget_events, rolling_weekly_splits, seasonal_scores,
)
from .matching import summarize_benchmark_events


@dataclass
class _SignalModel:
    forest: IsolationForest
    medians: np.ndarray
    threshold: float
    baseline: float
    score_min: float
    score_max: float


def household_groups(households: Sequence[str], seed: int) -> dict[str, list[str]]:
    names = sorted(set(households))
    if len(names) < 3 or len(names) != len(households):
        raise ValueError("Cross-household evaluation requires at least three distinct households")
    random.Random(seed).shuffle(names)
    train_count = min(len(names) - 2, max(1, int(len(names) * 0.7)))
    development_count = (len(names) - train_count) // 2
    return {
        "training": sorted(names[:train_count]),
        "development": sorted(names[train_count:train_count + development_count]),
        "test": sorted(names[train_count + development_count:]),
    }


def _fit_models(
    training: Sequence[SeriesPoint], calibration: Sequence[SeriesPoint],
) -> tuple[dict[str, _SignalModel], dict[str, dict]]:
    detector = IsolationForestAnomalyDetector()
    models: dict[str, _SignalModel] = {}
    support: dict[str, dict] = {}
    for signal, attribute in (("electricity", "electricity_kwh"), ("gas", "gas_m3")):
        train = [point for point in training if point.quality_flag == "ok" and getattr(point, attribute) is not None]
        cal = [point for point in calibration if point.quality_flag == "ok" and getattr(point, attribute) is not None]
        status = "sufficient_support"
        if len(train) < detector.minimum_samples:
            status = "insufficient_training_points"
        elif len(cal) < 10:
            status = "insufficient_calibration_points"
        support[signal] = {"status": status, "training_points": len(train), "calibration_points": len(cal)}
        if status != "sufficient_support":
            continue
        medians = detector._context_medians(train)
        forest = IsolationForest(contamination="auto", n_estimators=detector.n_estimators,
                                 random_state=detector.random_state)
        forest.fit(detector._features(train, attribute, medians))
        scores = forest.decision_function(detector._features(cal, attribute, medians))
        models[signal] = _SignalModel(
            forest=forest, medians=medians,
            threshold=float(np.quantile(scores, detector.contamination)),
            baseline=float(np.median([getattr(point, attribute) for point in train])),
            score_min=float(np.min(scores)), score_max=float(np.max(scores)),
        )
    return models, support


def _score_models(models: dict[str, _SignalModel], points: Sequence[SeriesPoint]) -> list[Event]:
    detector = IsolationForestAnomalyDetector()
    events: list[Event] = []
    for signal, model in models.items():
        attribute = "electricity_kwh" if signal == "electricity" else "gas_m3"
        valid = [point for point in points if point.quality_flag == "ok" and getattr(point, attribute) is not None]
        if not valid:
            continue
        scores = model.forest.decision_function(detector._features(valid, attribute, model.medians))
        found = []
        for point, score in zip(valid, scores):
            if score <= model.threshold:
                spread = model.score_max - model.score_min
                confidence = 1.0 if spread == 0 else max(0.0, min(1.0, (model.score_max - float(score)) / spread))
                found.append(detector._event(point, signal, float(getattr(point, attribute)), model.baseline,
                                             float(score), confidence))
        events.extend(detector._aggregate_events(found))
    return sorted(events, key=lambda event: event.start)


def _slice(points: Sequence[SeriesPoint], times: Sequence[datetime], start: datetime, end: datetime) -> list[SeriesPoint]:
    return list(points[bisect_left(times, start):bisect_left(times, end)])


def run_cross_household_benchmark(
    dataset: str,
    groups: dict[str, list[str]],
    evaluation_group: str,
    patterns: Sequence[str],
    seed: int,
    weather_gas_enabled: bool,
    strengths: Sequence[float],
    training_weeks: int | None,
    seed_repeats: int = 1,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Evaluate both models on identical injected held-out household readings."""
    if evaluation_group not in {"development", "test"}:
        raise ValueError("Evaluation group must be development or test")
    if seed_repeats not in {1, 3, 5}:
        raise ValueError("Seed repeats must be 1, 3, or 5")
    source_ids, target_ids = groups["training"], groups[evaluation_group]
    all_ids = groups["training"] + groups["development"] + groups["test"]
    if not source_ids or not target_ids or len(all_ids) != len(set(all_ids)):
        raise ValueError("Household groups must be nonempty and disjoint")
    series = get_series_many(dataset, set(source_ids + target_ids))
    if any(not points for points in series.values()):
        raise ValueError("A selected household has no readings")
    resolution = series[source_ids[0]][0].interval_minutes
    if any(point.interval_minutes != resolution for points in series.values() for point in points):
        raise ValueError("All households must have the same resolution")
    timestamps = {household: [point.timestamp for point in points] for household, points in series.items()}
    start = max(points[0].timestamp for points in series.values())
    end = min(points[-1].timestamp + timedelta(minutes=resolution) for points in series.values())
    template = _slice(series[source_ids[0]], timestamps[source_ids[0]], start, end)
    splits = rolling_weekly_splits(template, training_weeks) if training_weeks else [chronological_split(template)]
    results: list[dict] = []
    errors: list[dict] = []
    total = len(splits) * len(target_ids) * seed_repeats
    completed = 0
    if on_progress:
        on_progress(0, total)
    for index, split in enumerate(splits):
        train_start = split.training[0].timestamp
        calibration_start = split.calibration[0].timestamp
        test_start = split.test[0].timestamp
        test_end = split.test[-1].timestamp + timedelta(minutes=resolution)
        source_train = [point for household in source_ids for point in _slice(
            series[household], timestamps[household], train_start, calibration_start
        )]
        source_cal = [point for household in source_ids for point in _slice(
            series[household], timestamps[household], calibration_start, test_start
        )]
        shared_models, shared_support = _fit_models(source_train, source_cal)
        for household in target_ids:
            repeats_completed = 0
            try:
                target = series[household]
                training = _slice(target, timestamps[household], train_start, calibration_start)
                calibration = _slice(target, timestamps[household], calibration_start, test_start)
                test = _slice(target, timestamps[household], test_start, test_end)
                if not training or not calibration or not test:
                    raise ValueError("Missing training, calibration or test partition")
                personal_models, personal_support = _fit_models(training, calibration)
                supported = sorted(
                    signal for signal in shared_models.keys() & personal_models.keys()
                    if any(point.quality_flag == "ok" and getattr(
                        point, "electricity_kwh" if signal == "electricity" else "gas_m3"
                    ) is not None for point in test)
                )
                if not supported:
                    raise ValueError("No signal has enough data for both the personal and shared model")
                diagnostics = {
                    "isolation_forest": {signal: dict(info) for signal, info in personal_support.items()},
                    "shared_isolation_forest": {signal: dict(info) for signal, info in shared_support.items()},
                }
                for signal in ("electricity", "gas"):
                    for method in diagnostics:
                        diagnostics[method][signal] = {
                            **diagnostics[method][signal],
                            "test_points": sum(point.quality_flag == "ok" and getattr(
                                point, "electricity_kwh" if signal == "electricity" else "gas_m3"
                            ) is not None for point in test),
                        }
                hours = (test[-1].timestamp - test[0].timestamp).total_seconds() / 3600 + resolution / 60
                normal_outputs = {}
                for name, models in (("isolation_forest", personal_models), ("shared_isolation_forest", shared_models)):
                    normal = _score_models({signal: models[signal] for signal in supported}, test)
                    if name == "shared_isolation_forest":
                        normal = [event.model_copy(update={"method": name}) for event in normal]
                    normal_scores = summarize_benchmark_events(normal, [], hours, max(resolution, 15))
                    for metric in normal_scores["classes"]:
                        metric["alerts_per_household_week"] = round(metric["detected"] / (hours / 168), 4)
                    normal_outputs[name] = (normal, normal_scores)
                for repeat in range(seed_repeats):
                    injection_seed = seed + repeat
                    skipped: list[dict] = []
                    injected, truth = generate_benchmark_cases(
                        BenchmarkPartitions(source_train, source_cal, test), patterns, injection_seed,
                        weather_gas_enabled, strengths, "corrected_v2", skipped,
                    )
                    skipped.extend({
                        "pattern": "scoring", "signal": signal,
                        "reason": "not supported by both personal and shared models",
                    } for signal in ("electricity", "gas") if signal not in supported)
                    scored_truth = [event for event in truth if event.details["signal"] in supported]
                    methods = []
                    for name, models in (("isolation_forest", personal_models), ("shared_isolation_forest", shared_models)):
                        started = perf_counter()
                        selected = {signal: models[signal] for signal in supported}
                        normal, normal_scores = normal_outputs[name]
                        detected = _score_models(selected, injected)
                        if name == "shared_isolation_forest":
                            detected = [event.model_copy(update={"method": name}) for event in detected]
                        scores = summarize_benchmark_events(detected, scored_truth, hours, max(resolution, 15))
                        methods.append({
                            "method": name, "applicable": True, "supported_signals": supported,
                            "runtime_ms": round((perf_counter() - started) * 1000, 2),
                            "scores": scores, "normal_scores": normal_scores,
                            "detected_events": detected, "normal_events": normal,
                        })
                    controls = list(methods)
                    methods.append({
                        "method": "no_alert", "applicable": True, "supported_signals": supported,
                        "runtime_ms": 0, "scores": summarize_benchmark_events([], scored_truth, hours, max(resolution, 15)),
                        "normal_scores": {"classes": []}, "detected_events": [], "normal_events": [],
                    })
                    for control_index, method in enumerate(controls):
                        random_events = random_budget_events(test, method["normal_events"], injection_seed + control_index)
                        methods.append({
                            "method": "random_budget_" + method["method"], "applicable": True,
                            "supported_signals": supported, "runtime_ms": 0,
                            "scores": summarize_benchmark_events(random_events, scored_truth, hours, max(resolution, 15)),
                            "normal_scores": method["normal_scores"], "detected_events": random_events,
                            "normal_events": method["normal_events"],
                        })
                    result = {
                        "dataset": dataset, "household": household, "resolution_minutes": resolution,
                        "point_counts": {"training": len(training), "calibration": len(calibration), "test": len(test)},
                        "date_ranges": {
                            "training_start": train_start, "training_end": calibration_start - timedelta(minutes=resolution),
                            "calibration_start": calibration_start, "calibration_end": test_start - timedelta(minutes=resolution),
                            "test_start": test_start, "test_end": test_end - timedelta(minutes=resolution),
                        },
                        "seed": injection_seed, "protocol": "corrected_v2", "patterns": list(patterns),
                        "strengths": list(strengths), "training_weeks": training_weeks,
                        "week_index": index + 1 if training_weeks else None,
                        "skipped_injections": skipped, "detector_support": diagnostics,
                        "ground_truth": truth, "methods": methods,
                    }
                    result["seasonal"] = seasonal_scores(household, test, truth, methods, "corrected_v2")
                    results.append(result)
                    repeats_completed += 1
                    completed += 1
                    if on_progress:
                        on_progress(completed, total)
            except ValueError as error:
                errors.append({"household": household, "window": str(index + 1), "error": str(error)})
                completed += seed_repeats - repeats_completed
                if on_progress:
                    on_progress(completed, total)
    return results, errors
