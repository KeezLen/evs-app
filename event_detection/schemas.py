"""Shared JSON contracts for detection, series and evaluation."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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
    expected_elec_intervals: int = Field(default=96, gt=0)
    expected_gas_hours: int = Field(default=24, gt=0)
    electricity_basis: Literal['consumption', 'grid_import'] = 'consumption'
    electricity_export_kwh: float | None = None
    source_notes: list[str] = Field(default_factory=list)
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
    protocol: Literal["legacy_v1", "corrected_v2"] = "corrected_v2"
    household: str | None = "Klant 34"
    all_households: bool = False
    patterns: list[BenchmarkPattern] = Field(
        default_factory=lambda: ["spikes", "sustained_high", "low_use", "weather_gas"]
    )
    strengths: list[float] = Field(default_factory=lambda: [0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 2.0])
    seed: int = Field(default=17, ge=0)
    lookback_days: Literal[1, 7] = 1


class SaveBenchmarkRequest(BaseModel):
    result: dict[str, Any]


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


class HouseholdContext(BaseModel):
    energy_label: Literal["A++++", "A+++", "A++", "A+", "A", "B", "C", "D", "E", "F", "G"] | None = None
    floor_area_m2: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    work_schedule: str | None = Field(default=None, max_length=200)
    sleep_schedule: str | None = Field(default=None, max_length=200)


class ProfileRequest(BaseModel):
    dataset: str
    household: str
    range_start: datetime | None = None
    range_end: datetime | None = None
    home: HouseholdContext = Field(default_factory=HouseholdContext)
    building_bag_id: str | None = Field(default=None, pattern=r'^\d{16}$')
    building_confirmed: bool = False

    @model_validator(mode='after')
    def check_range(self):
        if self.building_bag_id and not self.building_confirmed:
            raise ValueError('Confirm that the selected building belongs to the selected household')
        if any(v is not None and v.tzinfo is not None for v in (self.range_start, self.range_end)):
            raise ValueError('Use timezone-naive timestamps matching the source data')
        if self.range_start and self.range_end and self.range_start > self.range_end:
            raise ValueError('range_start must not follow range_end')
        return self


class ProfileResponse(BaseModel):
    dataset: str
    profile: dict[str, Any]


class AddressSearchRequest(BaseModel):
    postcode: str = Field(min_length=6, max_length=12)
    house_number: int | None = Field(default=None, gt=0, le=99999)


class BuildingLookupRequest(BaseModel):
    bag_id: str = Field(pattern=r'^\d{16}$')
