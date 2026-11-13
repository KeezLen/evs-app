"""Standalone HTTP API for event detection."""

from collections import Counter
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from event_detection.config import settings
from event_detection.data import available_datasets, get_series
from event_detection.anomaly import IsolationForestAnomalyDetector
from event_detection.evaluation.matching import match_events
from event_detection.evaluation.scenarios import load_scenario
from event_detection.nilm import detector_registry
from event_detection.schemas import (
    DetectRequest,
    EvaluationMetric,
    EvaluationRequest,
    EvaluationResponse,
)

app = FastAPI(title=settings.api_title)
_ANOMALY_DETECTORS = {
    IsolationForestAnomalyDetector.name: IsolationForestAnomalyDetector(),
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_detector(module: str, method: str):
    """Resolve one detector from the public module/method pair."""
    if module == "nilm":
        return detector_registry.get(method)
    return _ANOMALY_DETECTORS[method]


@app.get("/")
def root():
    """Small landing response for a browser or service health check."""

    return {
        "service": settings.api_title,
        "status": "ok",
        "docs": "/docs",
        "endpoints": ["/datasets", "/series", "/detect", "/evaluate"],
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
        points = get_series(request.dataset, request.household, request.range_start, request.range_end)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        detector = _get_detector(request.module, request.method)
    except KeyError as error:
        detail = "Unknown NILM method" if request.module == "nilm" else "Unknown anomaly method"
        raise HTTPException(status_code=400, detail=detail) from error
    return detector.detect(points)


@app.get("/event-summary")
def event_summary(
    dataset: str,
    household: str,
    module: str = "anomaly",
    method: str = "isolation_forest",
    range_start: datetime | None = None,
    range_end: datetime | None = None,
):
    """Return detector results together with compact data-quality statistics."""
    try:
        points = get_series(dataset, household, range_start, range_end)
        detector = _get_detector(module, method)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except KeyError as error:
        detail = "Unknown NILM method" if module == "nilm" else "Unknown anomaly method"
        raise HTTPException(status_code=400, detail=detail) from error

    events = detector.detect(points)
    event_counts = Counter(event.type for event in events)
    quality_counts = Counter(point.quality_flag for point in points)
    test_split = None
    if isinstance(detector, IsolationForestAnomalyDetector):
        electricity_points = [
            point
            for point in points
            if point.quality_flag == "ok" and point.electricity_kwh is not None
        ]
        training_count = int(len(electricity_points) * detector.training_ratio)
        if training_count < len(electricity_points):
            test_split = {
                "timestamp": electricity_points[training_count].timestamp,
                "training_ratio": detector.training_ratio,
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
        "range_start": range_start,
        "range_end": range_end,
        "total_points": len(points),
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


@app.post("/evaluate", response_model=EvaluationResponse)
def evaluate(request: EvaluationRequest):
    """Compare the selected detector with one prepared synthetic scenario."""
    if request.dataset != "zonnedael":
        raise HTTPException(status_code=400, detail="Scenario evaluation is only available for Zonnedael")
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
    detected = detector.detect(points)
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
