"""Standalone HTTP API for event detection."""

from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from event_detection.config import settings
from event_detection.data import available_datasets, get_series
from event_detection.anomaly.placeholder import PlaceholderAnomalyDetector
from event_detection.nilm import detector_registry
from event_detection.schemas import (
    DetectRequest,
    EvaluationMetric,
    EvaluationRequest,
    EvaluationResponse,
)

app = FastAPI(title=settings.api_title)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    return available_datasets()


@app.get("/series")
def series(
    dataset: str,
    household: str,
    range_start: datetime | None = None,
    range_end: datetime | None = None,
):
    return get_series(dataset, household, range_start, range_end)


@app.post("/detect")
def detect(request: DetectRequest):
    points = get_series(request.dataset, request.household, request.range_start, request.range_end)
    if request.module == "nilm":
        try:
            detector = detector_registry.get(request.method)
        except KeyError as error:
            raise HTTPException(status_code=400, detail="Unknown NILM method") from error
    else:
        detector = PlaceholderAnomalyDetector()
    return detector.detect(points)


@app.post("/evaluate", response_model=EvaluationResponse)
def evaluate(request: EvaluationRequest):
    del request
    return EvaluationResponse(
        metrics=[
            EvaluationMetric(
                event_type=event_type,
                precision=0,
                recall=0,
                f1=0,
                detected=0,
                ground_truth=0,
                matched=0,
            )
            for event_type in ("step_change", "high_power_appliance", "base_load_change", "gas_event")
        ],
        tolerance_minutes=settings.default_tolerance_minutes,
        source="unavailable: no dataset labels or synthetic ground truth have been configured",
        notes=["Evaluation is a placeholder until the data loader reports its ground-truth source."],
    )
