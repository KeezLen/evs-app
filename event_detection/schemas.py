"""Shared JSON contracts for detection, series and evaluation."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ModuleName = Literal["nilm", "anomaly"]
EvaluationScenario = Literal["normal", "high_use", "missing", "incomplete"]
BenchmarkPattern = Literal["spikes", "sustained_high", "low_use", "weather_gas"]


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
    interval_minutes: int = Field(default=1440, gt=0)
    electricity_kwh: float | None = None
    gas_m3: float | None = None
    quality_flag: Literal["ok", "partial", "missing"]
    n_elec_intervals: int | None = None
    n_gas_hours: int | None = None
    temp_mean_c: float | None = None
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    hdd18: float | None = None
    woning_type: str | None = None
    bouwjaar_band: str | None = None
    gezinssituatie: str | None = None


class DetectRequest(BaseModel):
    dataset: str
    household: str
    range_start: datetime | None = None
    range_end: datetime | None = None
    module: ModuleName
    method: str = "rules"
    lookback_days: Literal[1, 7] = 1


class EvaluationRequest(DetectRequest):
    tolerance_minutes: int = Field(default=1440, ge=0)
    scenario: EvaluationScenario = "high_use"


class BenchmarkRequest(BaseModel):
    dataset: str
    household: str | None = "Klant 34"
    all_households: bool = False
    patterns: list[BenchmarkPattern] = Field(
        default_factory=lambda: ["spikes", "sustained_high", "low_use", "weather_gas"]
    )
    strengths: list[float] = Field(default_factory=lambda: [0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 2.0])
    seed: int = Field(default=17, ge=0)
    lookback_days: Literal[1, 7] = 1


class EvaluationMetric(BaseModel):
    event_type: str
    precision: float
    recall: float
    f1: float
    detected: int
    ground_truth: int
    matched: int


class DataQualityIssue(BaseModel):
    date: datetime
    status: Literal["missing", "partial", "gap"]
    details: str


class EvaluationResponse(BaseModel):
    metrics: list[EvaluationMetric]
    tolerance_minutes: int
    source: str
    notes: list[str] = Field(default_factory=list)
    data_quality: list[DataQualityIssue] = Field(default_factory=list)
