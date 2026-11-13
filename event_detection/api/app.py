"""Standalone HTTP API for event detection."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import RLock
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from event_detection.config import settings
from event_detection.data import available_datasets, get_series
from event_detection.anomaly import IsolationForestAnomalyDetector, RNNForecastDetector
from event_detection.evaluation.matching import match_events
from event_detection.evaluation.benchmark import run_household_benchmark
from event_detection.evaluation.scenarios import load_scenario
from event_detection.evaluation.weather_audit import audit_weather_linkage
from event_detection.nilm import detector_registry
from event_detection.schemas import (
    DetectRequest,
    BenchmarkRequest,
    EvaluationMetric,
    EvaluationRequest,
    EvaluationResponse,
)

app = FastAPI(title=settings.api_title)
_ANOMALY_DETECTORS = {
    IsolationForestAnomalyDetector.name: IsolationForestAnomalyDetector(),
    RNNForecastDetector.name: RNNForecastDetector(),
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
_BENCHMARK_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="event-benchmark")
_BENCHMARK_JOBS: dict[str, dict] = {}
_BENCHMARK_JOBS_LOCK = RLock()


def _get_detector(module: str, method: str):
    """Resolve one detector from the public module/method pair."""
    if module == "nilm":
        return detector_registry.get(method)
    return _ANOMALY_DETECTORS[method]


def _detector_points(
    dataset: str,
    household: str,
    module: str,
    range_end: datetime | None,
    range_start: datetime | None,
):
    """Load preceding history for anomaly detection windows when available."""
    if module == "anomaly" and range_start is not None:
        return get_series(dataset, household, range_end=range_end)
    return get_series(dataset, household, range_start, range_end)


def _detect_with_window(
    detector,
    points,
    module: str,
    detection_start: datetime | None,
    lookback_days: int = 1,
):
    if isinstance(detector, RNNForecastDetector):
        return detector.detect(
            points,
            detection_start=detection_start,
            lookback_days=lookback_days,
        )
    if module == "anomaly" and detection_start is not None:
        return detector.detect(points, detection_start=detection_start)
    return detector.detect(points)


def _validate_resolution(detector, points) -> None:
    if isinstance(detector, RNNForecastDetector) and points and points[0].interval_minutes not in {15, 60}:
        raise HTTPException(
            status_code=400,
            detail="RNN forecast currently supports hourly and 15-minute data only",
        )


@app.get("/")
def root():
    """Small landing response for a browser or service health check."""

    return {
        "service": settings.api_title,
        "status": "ok",
        "docs": "/docs",
        "endpoints": ["/datasets", "/series", "/detect", "/evaluate", "/benchmark"],
    }


@app.get("/datasets")
def datasets():
    """List the datasets known by the service."""
    return available_datasets()


@app.get("/series")
def series(
    dataset: str,
    household: str,
    range_start: datetime | None = None,
    range_end: datetime | None = None,
):
    """Return one household's daily readings."""
    try:
        return get_series(dataset, household, range_start, range_end)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/detect")
def detect(request: DetectRequest):
    """Run the selected detector for one household and date range."""
    try:
        points = _detector_points(
            request.dataset,
            request.household,
            request.module,
            request.range_end,
            request.range_start,
        )
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        detector = _get_detector(request.module, request.method)
    except KeyError as error:
        detail = "Unknown NILM method" if request.module == "nilm" else "Unknown anomaly method"
        raise HTTPException(status_code=400, detail=detail) from error
    _validate_resolution(detector, points)
    return _detect_with_window(
        detector,
        points,
        request.module,
        request.range_start,
        request.lookback_days,
    )


@app.get("/event-summary")
def event_summary(
    dataset: str,
    household: str,
    module: str = "anomaly",
    method: str = "isolation_forest",
    range_start: datetime | None = None,
    range_end: datetime | None = None,
    lookback_days: int = 1,
):
    """Return detector results together with compact data-quality statistics."""
    if lookback_days not in {1, 7}:
        raise HTTPException(status_code=422, detail="lookback_days must be 1 or 7")
    try:
        points = _detector_points(dataset, household, module, range_end, range_start)
        display_points = get_series(dataset, household, range_start, range_end)
        detector = _get_detector(module, method)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except KeyError as error:
        detail = "Unknown NILM method" if module == "nilm" else "Unknown anomaly method"
        raise HTTPException(status_code=400, detail=detail) from error

    _validate_resolution(detector, points)
    events = _detect_with_window(detector, points, module, range_start, lookback_days)
    event_counts = Counter(event.type for event in events)
    quality_counts = Counter(point.quality_flag for point in display_points)
    test_split = None
    if isinstance(detector, (IsolationForestAnomalyDetector, RNNForecastDetector)):
        electricity_points = [
            point
            for point in points
            if point.quality_flag == "ok" and point.electricity_kwh is not None
        ]
        training_ratio = getattr(detector, "training_ratio", 0.7)
        training_count = int(len(electricity_points) * training_ratio)
        if range_start is not None:
            requested_training_count = next(
                (index for index, point in enumerate(electricity_points) if point.timestamp >= range_start),
                len(electricity_points),
            )
            minimum_training_points = (
                (lookback_days * 1440 // electricity_points[0].interval_minutes)
                + max(1, 60 // electricity_points[0].interval_minutes)
                + detector.minimum_training_windows
                - 1
                if isinstance(detector, RNNForecastDetector) and electricity_points
                else detector.minimum_samples
            )
            if (
                requested_training_count >= minimum_training_points
                and requested_training_count < len(electricity_points)
            ):
                training_count = requested_training_count
        if training_count < len(electricity_points):
            test_split = {
                "timestamp": electricity_points[training_count].timestamp,
                "training_ratio": training_count / len(electricity_points),
                "training_points": training_count,
                "detection_points": len(electricity_points) - training_count,
            }
    duration_minutes = sum(
        int((event.end - event.start).total_seconds() / 60)
        for event in events
    )
    return {
        "dataset": dataset,
        "household": household,
        "module": module,
        "method": method,
        "lookback_days": lookback_days if isinstance(detector, RNNForecastDetector) else None,
        "range_start": range_start,
        "range_end": range_end,
        "total_points": len(display_points),
        "valid_points": quality_counts.get("ok", 0),
        "partial_points": quality_counts.get("partial", 0),
        "missing_points": quality_counts.get("missing", 0),
        "event_count": len(events),
        "events_by_type": dict(sorted(event_counts.items())),
        "anomalous_duration_minutes": duration_minutes,
        "test_split": test_split,
        "events": events,
    }


@app.get("/series-range")
def series_range(dataset: str, household: str):
    """Return the recorded date bounds for one dataset and household."""
    try:
        points = get_series(dataset, household)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not points:
        raise HTTPException(status_code=404, detail="No readings found for this household")
    return {
        "dataset": dataset,
        "household": household,
        "start": points[0].timestamp,
        "end": points[-1].timestamp,
        "start_date": points[0].timestamp.date(),
        "end_date": points[-1].timestamp.date(),
        "resolution_minutes": points[0].interval_minutes,
        "point_count": len(points),
    }


def _benchmark_aggregate(results: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for result in results:
        for method in result["methods"]:
            if not method.get("applicable"):
                continue
            for metric in method["scores"]["classes"]:
                key = (method["method"], metric["signal"], metric["direction"])
                grouped.setdefault(key, []).append({
                    **metric,
                    "household": result["household"],
                    "normal_events_per_week": next(
                        (
                            normal_metric["alerts_per_household_week"]
                            for normal_metric in method["normal_scores"]["classes"]
                            if normal_metric["signal"] == metric["signal"]
                            and normal_metric["direction"] == metric["direction"]
                        ),
                        0.0,
                    ),
                })
    aggregate = []
    for (method, signal, direction), rows in sorted(grouped.items()):
        aggregate.append({
            "method": method,
            "signal": signal,
            "direction": direction,
            "households": len(rows),
            "macro_precision": round(sum(row["precision"] for row in rows) / len(rows), 4),
            "macro_recall": round(sum(row["recall"] for row in rows) / len(rows), 4),
            "macro_f1": round(sum(row["f1"] for row in rows) / len(rows), 4),
            "mean_unmatched_injected_events": round(sum(row["false_positives"] for row in rows) / len(rows), 3),
            "mean_no_injection_events_per_week": round(
                sum(row["normal_events_per_week"] for row in rows) / len(rows), 3
            ),
        })
    return aggregate


def _run_benchmark_job(
    job_id: str,
    request: BenchmarkRequest,
    households: list[str],
    weather_audit: dict,
) -> None:
    with _BENCHMARK_JOBS_LOCK:
        _BENCHMARK_JOBS[job_id]["status"] = "running"
    results: list[dict] = []
    errors: list[dict[str, str]] = []
    for index, household in enumerate(households):
        try:
            result = run_household_benchmark(
                request.dataset,
                household,
                request.patterns,
                request.seed,
                bool(weather_audit["weather_gas_enabled"]),
                request.lookback_days,
                request.strengths,
            )
            results.append(result)
        except Exception as error:
            errors.append({"household": household, "error": str(error)})
        with _BENCHMARK_JOBS_LOCK:
            _BENCHMARK_JOBS[job_id].update({
                "completed_households": index + 1,
                "current_household": household,
                "results": results,
                "errors": errors,
            })
    with _BENCHMARK_JOBS_LOCK:
        _BENCHMARK_JOBS[job_id].update({
            "status": "completed" if results else "failed",
            "aggregate": _benchmark_aggregate(results),
            "weather_audit": weather_audit,
        })


@app.get("/benchmark/weather-audit")
def benchmark_weather_audit(household: str = "Klant 34"):
    """Audit daily/hourly weather and gas alignment before weather scenarios."""
    try:
        return audit_weather_linkage(household)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/benchmark")
def start_benchmark(request: BenchmarkRequest):
    """Run one household now, or queue all included households with progress."""
    allowed_strengths = {0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 2.0}
    if not request.patterns:
        raise HTTPException(status_code=400, detail="Select at least one benchmark pattern")
    if not request.strengths or not set(request.strengths) <= allowed_strengths:
        raise HTTPException(status_code=400, detail="Unsupported injection strength")
    dataset_info = next((item for item in available_datasets() if item.id == request.dataset), None)
    if dataset_info is None or not dataset_info.available:
        raise HTTPException(status_code=400, detail="Unknown or unavailable benchmark dataset")
    if request.all_households:
        households = dataset_info.households
    elif request.household:
        households = [request.household]
    else:
        raise HTTPException(status_code=400, detail="Select a household or enable all households")
    if not households:
        raise HTTPException(status_code=400, detail="No included households are available for this dataset")
    audit_household = "Klant 34" if "Klant 34" in households else households[0]
    try:
        weather_audit = audit_weather_linkage(audit_household)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if request.all_households:
        job_id = uuid4().hex
        with _BENCHMARK_JOBS_LOCK:
            _BENCHMARK_JOBS[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "total_households": len(households),
                "completed_households": 0,
                "current_household": None,
                "results": [],
                "errors": [],
                "weather_audit": weather_audit,
            }
        _BENCHMARK_EXECUTOR.submit(_run_benchmark_job, job_id, request, households, weather_audit)
        return {"job_id": job_id, "status": "queued", "total_households": len(households)}
    try:
        result = run_household_benchmark(
            request.dataset,
            households[0],
            request.patterns,
            request.seed,
            bool(weather_audit["weather_gas_enabled"]),
            request.lookback_days,
            request.strengths,
        )
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "status": "completed",
        "weather_audit": weather_audit,
        "results": [result],
        "aggregate": _benchmark_aggregate([result]),
    }


@app.get("/benchmark/jobs/{job_id}")
def benchmark_job(job_id: str):
    with _BENCHMARK_JOBS_LOCK:
        job = _BENCHMARK_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Benchmark job not found")
        return job


@app.post("/evaluate", response_model=EvaluationResponse)
def evaluate(request: EvaluationRequest):
    """Compare the selected detector with one prepared synthetic scenario."""
    if request.dataset != "zonnedael":
        raise HTTPException(status_code=400, detail="Scenario evaluation is only available for Zonnedael")
    if request.module == "anomaly" and request.method == RNNForecastDetector.name:
        raise HTTPException(
            status_code=400,
            detail="RNN evaluation is not available for the daily-only scenario fixtures",
        )
    # Scenarios currently contain prepared data for this home only.
    fixture_household = "Klant 34"
    try:
        points, ground_truth, quality = load_scenario(request.scenario, fixture_household)
        detector = _get_detector(request.module, request.method)
    except (FileNotFoundError, KeyError, ValueError) as error:
        detail = "Unknown NILM method" if request.module == "nilm" else "Unknown anomaly method"
        raise HTTPException(status_code=400, detail=detail) from error
    # Apply the requested date range to both detections and truth.
    points = [
        point for point in points
        if (request.range_start is None or point.timestamp >= request.range_start)
        and (request.range_end is None or point.timestamp <= request.range_end)
    ]
    ground_truth = [
        event for event in ground_truth
        if (request.range_start is None or event.start >= request.range_start)
        and (request.range_end is None or event.start <= request.range_end)
    ]
    if request.module == "anomaly":
        # Scenario fixtures use the rules vocabulary; map it for anomaly metrics.
        event_type_map = {
            "high_electricity": "unusual_electricity",
            "high_gas": "unusual_gas",
        }
        ground_truth = [
            event.model_copy(update={"type": event_type_map.get(event.type, event.type)})
            for event in ground_truth
        ]
    detected = _detect_with_window(
        detector,
        points,
        request.module,
        request.range_start,
        request.lookback_days,
    )
    event_types = sorted({event.type for event in detected} | {event.type for event in ground_truth})
    metrics = []
    for event_type in event_types:
        # Calculate each event type separately so unrelated patterns do not mix.
        result = match_events(
            [event for event in detected if event.type == event_type],
            [event for event in ground_truth if event.type == event_type],
            request.tolerance_minutes,
        )
        precision = result["matched"] / result["detected"] if result["detected"] else 0
        recall = result["matched"] / result["ground_truth"] if result["ground_truth"] else 0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        metrics.append(EvaluationMetric(
            event_type=event_type,
            precision=round(precision, 3),
            recall=round(recall, 3),
            f1=round(f1, 3),
            **result,
        ))
    return EvaluationResponse(
        metrics=metrics,
        tolerance_minutes=request.tolerance_minutes,
        source=(
            f"synthetic ground truth from Zonnedael scenario '{request.scenario}' "
            f"for {fixture_household} using '{request.method}'"
        ),
        notes=[
            "Synthetic events are evaluation fixtures, not appliance labels.",
            "Partial, missing, and absent dates are reported as data quality and excluded from detection.",
        ],
        data_quality=quality,
    )
