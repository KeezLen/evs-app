"""Shared JSON contracts for detection, series and evaluation."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ModuleName = Literal["nilm", "anomaly"]


class Event(BaseModel):
    id: str
    type: str
    start: datetime
    end: datetime
    magnitude: float
    confidence: float = Field(ge=0, le=1)
    method: str
    details: dict[str, Any] = Field(default_factory=dict)


class DatasetInfo(BaseModel):
    id: str
    name: str
    households: list[str] = Field(default_factory=list)
    resolution_minutes: int
    available: bool
    notes: str


class SeriesPoint(BaseModel):
    timestamp: datetime
    electricity_w: float | None = None
    gas_value: float | None = None
    gas_unit: str | None = None


class DetectRequest(BaseModel):
    dataset: str
    household: str
    range_start: datetime | None = None
    range_end: datetime | None = None
    module: ModuleName
    method: str = "rules"


class EvaluationRequest(DetectRequest):
    tolerance_minutes: int = Field(default=15, ge=0)


class EvaluationMetric(BaseModel):
    event_type: str
    precision: float
    recall: float
    f1: float
    detected: int
    ground_truth: int
    matched: int


class EvaluationResponse(BaseModel):
    metrics: list[EvaluationMetric]
    tolerance_minutes: int
    source: str
    notes: list[str] = Field(default_factory=list)
