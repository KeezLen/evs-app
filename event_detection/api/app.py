"""Standalone HTTP API for event detection."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware

from event_detection.config import settings
from event_detection.data import available_datasets, dataset_fingerprints, get_series
from event_detection.anomaly import IsolationForestAnomalyDetector, RNNForecastDetector
from event_detection.evaluation.matching import match_events
from event_detection.evaluation.benchmark import run_household_benchmark, run_household_rolling_benchmark
from event_detection.evaluation.cross_household import household_groups, run_cross_household_benchmark
from event_detection.evaluation.scenarios import load_scenario
from event_detection.evaluation.weather_audit import audit_weather_linkage
from event_detection.nilm import detector_registry
from event_detection.schemas import (
    DetectRequest,
    BenchmarkRequest,
    EvaluationMetric,
    EvaluationRequest,
    EvaluationResponse,
    SaveBenchmarkRequest,
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
_BENCHMARK_RESULT_DIR = Path(__file__).resolve().parents[2] / "benchmark_results"


def _saved_benchmark_metadata(record: dict) -> dict:
    metadata = {key: record.get(key) for key in (
        "id", "saved_at", "source", "status", "dataset", "protocol", "seed",
        "households_completed", "households_requested", "error_count",
    )}
    result = record.get("result", {})
    first_result = next(iter(result.get("results", [])), {})
    for key in ("seed", "lookback_days", "training_weeks", "patterns", "strengths",
                "comparison", "evaluation_group", "household_seed", "seed_repeats"):
        if metadata.get(key) is None:
            metadata[key] = result.get(key)
        if metadata[key] is None:
            metadata[key] = first_result.get(key)
    return metadata


def _persist_benchmark_result(result: dict, source: str) -> dict:
    """Atomically store a completed benchmark result and return its index metadata."""
    result_data = jsonable_encoder(result)
    result_id = uuid4().hex
    saved_at = datetime.now(timezone.utc).isoformat()
    first_result = next(iter(result_data.get("results", [])), {})
    record = {
        "id": result_id,
        "saved_at": saved_at,
        "source": source,
        "status": result_data.get("status", "completed"),
        "dataset": result_data.get("dataset", first_result.get("dataset")),
        "protocol": result_data.get("protocol", first_result.get("protocol", "unknown")),
        "seed": result_data.get("seed", first_result.get("seed")),
        "households_completed": len({row.get("household") for row in result_data.get("results", [])}),
        "households_requested": result_data.get("total_households", len(result_data.get("results", []))),
        "error_count": len(result_data.get("errors", [])),
        "result": result_data,
    }
    _BENCHMARK_RESULT_DIR.mkdir(parents=True, exist_ok=True)
    target = _BENCHMARK_RESULT_DIR / f"{result_id}.json"
    temporary = _BENCHMARK_RESULT_DIR / f".{result_id}.tmp"
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=True), encoding="utf-8")
    temporary.replace(target)
    return _saved_benchmark_metadata(record)


def _saved_benchmark_path(result_id: str) -> Path:
    if not result_id or any(character not in "0123456789abcdef" for character in result_id.lower()):
        raise HTTPException(status_code=404, detail="Saved benchmark result not found")
    return _BENCHMARK_RESULT_DIR / f"{result_id}.json"


def _read_saved_benchmark_result(result_id: str) -> dict:
    path = _saved_benchmark_path(result_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Saved benchmark result not found") from error


def _list_saved_benchmark_results() -> list[dict]:
    if not _BENCHMARK_RESULT_DIR.exists():
        return []
    records = [json.loads(path.read_text(encoding="utf-8")) for path in _BENCHMARK_RESULT_DIR.glob("*.json")]
    records.sort(key=lambda record: record.get("saved_at", ""), reverse=True)
    return [_saved_benchmark_metadata(record) for record in records]


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
        by_household: dict[str, list[dict]] = {}
        for row in rows:
            by_household.setdefault(row["household"], []).append(row)

        def household_means(name: str) -> list[float]:
            means = []
            for household_rows in by_household.values():
                values = [row[name] for row in household_rows if row[name] is not None]
                if values:
                    means.append(sum(values) / len(values))
            return means

        def metric_mean(name: str) -> float | None:
            values = household_means(name)
            return round(sum(values) / len(values), 4) if values else None

        aggregate.append({
            "method": method,
            "signal": signal,
            "direction": direction,
            "households": len(by_household),
            "windows": len(rows),
            "macro_precision": metric_mean("precision"),
            "macro_recall": metric_mean("recall"),
            "macro_f1": metric_mean("f1"),
            "precision_households": len(household_means("precision")),
            "recall_households": len(household_means("recall")),
            "f1_households": len(household_means("f1")),
            "detected": sum(row["detected"] for row in rows),
            "ground_truth": sum(row["ground_truth"] for row in rows),
            "matched": sum(row["matched"] for row in rows),
            "mean_unmatched_injected_events": round(sum(household_means("false_positives")) / len(by_household), 3),
            "mean_no_injection_events_per_week": round(sum(household_means("normal_events_per_week")) / len(by_household), 3),
        })
    return aggregate


def _seasonal_aggregate(results: list[dict]) -> list[dict]:
    seasons: dict[str, list[dict]] = {}
    for result in results:
        for segment in result.get("seasonal", []):
            seasons.setdefault(segment["season"], []).append(segment)
    return [{
        "season": season,
        "start": min(segment["start"] for segment in segments),
        "end": max(segment["end"] for segment in segments),
        "windows": len(segments),
        "households": len({segment["household"] for segment in segments}),
        "valid_electricity_points": sum(segment["valid_electricity_points"] for segment in segments),
        "valid_gas_points": sum(segment["valid_gas_points"] for segment in segments),
        "excluded_boundary_events": sum(segment["excluded_boundary_events"] for segment in segments),
        "aggregate": _benchmark_aggregate(segments),
    } for season, segments in sorted(seasons.items(), key=lambda item: min(segment["start"] for segment in item[1]))]


def _seed_aggregates(results: list[dict], include_seasonal: bool) -> list[dict]:
    seeds = sorted({result["seed"] for result in results})
    return [{
        "seed": seed,
        "aggregate": _benchmark_aggregate([result for result in results if result["seed"] == seed]),
        "seasonal_aggregate": _seasonal_aggregate([result for result in results if result["seed"] == seed]) if include_seasonal else [],
    } for seed in seeds]


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
        with _BENCHMARK_JOBS_LOCK:
            _BENCHMARK_JOBS[job_id].update({
                "current_household": household,
                "completed_weeks": 0,
                "total_weeks": None,
            })
        try:
            args = (
                request.dataset, household, request.patterns, request.seed,
                bool(weather_audit["weather_gas_enabled"]), request.lookback_days,
                request.strengths, request.protocol,
            )
            if request.training_weeks is None:
                results.append(run_household_benchmark(*args))
            else:
                def report_progress(completed: int, total: int) -> None:
                    with _BENCHMARK_JOBS_LOCK:
                        _BENCHMARK_JOBS[job_id].update({
                            "completed_weeks": completed, "total_weeks": total,
                        })

                results.extend(run_household_rolling_benchmark(
                    *args, request.training_weeks, on_progress=report_progress,
                ))
        except Exception as error:
            errors.append({"household": household, "error": str(error)})
        with _BENCHMARK_JOBS_LOCK:
            _BENCHMARK_JOBS[job_id].update({
                "completed_households": index + 1,
                "current_household": household,
                "results": results.copy(),
                "errors": errors.copy(),
                "completed_weeks": 0,
                "total_weeks": None,
            })
    completed_job = {
        "job_id": job_id,
        "status": "completed" if results else "failed",
        "total_households": len(households),
        "all_households": request.all_households,
        "completed_households": len(households),
        "results": results,
        "errors": errors,
        "aggregate": _benchmark_aggregate(results),
        "seasonal_aggregate": _seasonal_aggregate(results) if request.seasonal_breakdown else [],
        "weather_audit": weather_audit,
        "protocol": request.protocol,
        "dataset": request.dataset,
        "patterns": request.patterns,
        "strengths": request.strengths,
        "seed": request.seed,
        "lookback_days": request.lookback_days,
        "training_weeks": request.training_weeks,
        "seasonal_breakdown": request.seasonal_breakdown,
        "comparison": "personal",
    }
    try:
        saved_metadata = _persist_benchmark_result(completed_job, "background")
        completed_job.update(saved_metadata)
        completed_job["saved_result_id"] = saved_metadata["id"]
    except OSError as error:
        completed_job["save_error"] = str(error)
    with _BENCHMARK_JOBS_LOCK:
        _BENCHMARK_JOBS[job_id].update(completed_job)


def _run_cross_benchmark_job(job_id: str, request: BenchmarkRequest, groups: dict[str, list[str]],
                             weather_audit: dict) -> None:
    with _BENCHMARK_JOBS_LOCK:
        _BENCHMARK_JOBS[job_id]["status"] = "running"

    def report_progress(completed: int, total: int) -> None:
        with _BENCHMARK_JOBS_LOCK:
            _BENCHMARK_JOBS[job_id].update({"completed_windows": completed, "total_windows": total})

    try:
        fingerprints = dataset_fingerprints(request.dataset)
        results, errors = run_cross_household_benchmark(
            request.dataset, groups, request.evaluation_group, request.patterns, request.seed,
            bool(weather_audit["weather_gas_enabled"]), request.strengths,
            request.training_weeks, seed_repeats=request.seed_repeats, on_progress=report_progress,
        )
    except Exception as error:
        fingerprints = None
        results, errors = [], [{"household": "experiment", "error": str(error)}]
    total_households = len(groups[request.evaluation_group])
    completed_job = {
        "job_id": job_id, "status": "completed" if results else "failed",
        "dataset": request.dataset, "protocol": request.protocol,
        "experiment_version": "cross_household_v1", "dataset_fingerprints": fingerprints,
        "comparison": request.comparison, "evaluation_group": request.evaluation_group,
        "household_seed": request.household_seed, "household_groups": groups,
        "total_households": total_households, "completed_households": total_households,
        "all_households": True, "results": results, "errors": errors,
        "aggregate": _benchmark_aggregate(results),
        "seasonal_aggregate": _seasonal_aggregate(results) if request.seasonal_breakdown else [],
        "seed_aggregates": _seed_aggregates(results, request.seasonal_breakdown),
        "seasonal_breakdown": request.seasonal_breakdown,
        "weather_audit": weather_audit, "patterns": request.patterns, "strengths": request.strengths,
        "seed": request.seed, "seed_repeats": request.seed_repeats,
        "lookback_days": request.lookback_days, "training_weeks": request.training_weeks,
    }
    try:
        saved = _persist_benchmark_result(completed_job, "background")
        completed_job.update(saved)
        completed_job["saved_result_id"] = saved["id"]
    except OSError as error:
        completed_job["save_error"] = str(error)
    with _BENCHMARK_JOBS_LOCK:
        _BENCHMARK_JOBS[job_id].update(completed_job)


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
    if request.comparison == "cross_household":
        if request.protocol != "corrected_v2":
            raise HTTPException(status_code=400, detail="Cross-household comparison requires corrected_v2")
        if request.training_weeks is not None and dataset_info.resolution_minutes == 1440:
            raise HTTPException(
                status_code=400,
                detail="Daily rolling comparisons have fewer than 10 calibration observations; use hourly or quarter-hour data",
            )
        try:
            groups = household_groups(dataset_info.households, request.household_seed)
            weather_audit = audit_weather_linkage("Klant 34" if "Klant 34" in dataset_info.households else dataset_info.households[0])
        except (FileNotFoundError, ValueError, IndexError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        job_id = uuid4().hex
        total_households = len(groups[request.evaluation_group])
        with _BENCHMARK_JOBS_LOCK:
            _BENCHMARK_JOBS[job_id] = {
                "job_id": job_id, "protocol": request.protocol, "comparison": request.comparison,
                "status": "queued", "total_households": total_households, "completed_households": 0,
                "completed_windows": 0, "total_windows": None, "results": [], "errors": [],
                "household_groups": groups, "evaluation_group": request.evaluation_group,
                "weather_audit": weather_audit,
            }
        _BENCHMARK_EXECUTOR.submit(_run_cross_benchmark_job, job_id, request, groups, weather_audit)
        return {"job_id": job_id, "status": "queued", "total_households": total_households, "protocol": request.protocol}
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
    if request.all_households or request.training_weeks is not None:
        job_id = uuid4().hex
        with _BENCHMARK_JOBS_LOCK:
            _BENCHMARK_JOBS[job_id] = {
                "job_id": job_id,
                "protocol": request.protocol,
                "status": "queued",
                "total_households": len(households),
                "completed_households": 0,
                "current_household": None,
                "results": [],
                "errors": [],
                "weather_audit": weather_audit,
            }
        _BENCHMARK_EXECUTOR.submit(_run_benchmark_job, job_id, request, households, weather_audit)
        return {"job_id": job_id, "status": "queued", "total_households": len(households), "protocol": request.protocol}
    try:
        result = run_household_benchmark(
            request.dataset,
            households[0],
            request.patterns,
            request.seed,
            bool(weather_audit["weather_gas_enabled"]),
            request.lookback_days,
            request.strengths,
            request.protocol,
        )
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    response_data = {
        "status": "completed",
        "protocol": request.protocol,
        "weather_audit": weather_audit,
        "results": [result],
        "aggregate": _benchmark_aggregate([result]),
        "seasonal_aggregate": _seasonal_aggregate([result]) if request.seasonal_breakdown else [],
        "seasonal_breakdown": request.seasonal_breakdown,
        "comparison": "personal",
    }
    try:
        response_data.update(_persist_benchmark_result(response_data, "automatic"))
    except OSError as error:
        response_data["save_error"] = str(error)
    return response_data


@app.get("/benchmark/jobs/{job_id}")
def benchmark_job(job_id: str):
    with _BENCHMARK_JOBS_LOCK:
        job = _BENCHMARK_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Benchmark job not found")
        return job.copy()


@app.get("/benchmark/saved")
def saved_benchmarks():
    """List saved benchmark runs, newest first."""
    return _list_saved_benchmark_results()


@app.get("/benchmark/saved/{result_id}")
def saved_benchmark(result_id: str):
    """Return a saved benchmark run and all its household results."""
    return _read_saved_benchmark_result(result_id)


@app.delete("/benchmark/saved/{result_id}")
def delete_saved_benchmark(result_id: str):
    """Delete one saved benchmark run."""
    path = _saved_benchmark_path(result_id)
    try:
        path.unlink()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Saved benchmark result not found") from error
    except OSError as error:
        raise HTTPException(status_code=500, detail=f"Could not delete benchmark result: {error}") from error
    return {"id": result_id, "deleted": True}


@app.post("/benchmark/saved")
def save_benchmark(request: SaveBenchmarkRequest):
    """Persist a completed result currently held by a benchmark page."""
    if request.result.get("status") not in {"completed", "failed"} or not isinstance(request.result.get("results"), list):
        raise HTTPException(status_code=400, detail="Only a completed benchmark result can be saved")
    try:
        return _persist_benchmark_result(request.result, "manual")
    except OSError as error:
        raise HTTPException(status_code=500, detail=f"Could not save benchmark result: {error}") from error


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
