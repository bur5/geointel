from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DashboardModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Geography(DashboardModel):
    name: str | None
    iso3: str | None
    region: str | None
    unit: str | None


class Provenance(DashboardModel):
    provider: str | None = None
    source_record_id: str | None = None
    analysis_run_id: UUID | None = None
    version: str | None = None
    retrieved_at: datetime | None = None


class Point(DashboardModel):
    id: UUID
    geography: Geography
    provenance: Provenance
    freshness: Literal["recent", "stale", "unknown"]


class Observation(Point):
    kind: Literal["observed_event"] = "observed_event"
    occurred_at: datetime | None
    event_type: str
    reported_fatalities: int | None
    temporal_classification: str | None
    confidence: str


class UCDPObservation(Point):
    kind: Literal["observed_event"] = "observed_event"
    occurred_at: datetime | None
    ended_at: datetime | None
    dataset: str | None
    temporal_role: str
    coverage_end: datetime | None
    violence_type_code: int | None
    gw_country_code: int | None
    reported_fatalities_best: int | None
    reported_fatalities_low: int | None
    reported_fatalities_high: int | None
    reliability: str


class IndicatorPoint(Point):
    kind: Literal["derived_indicator"] = "derived_indicator"
    observed_at: datetime | None
    name: str
    value: float | None
    unit: str | None


class Prediction(Point):
    kind: Literal["model_prediction"] = "model_prediction"
    issued_at: datetime
    target_start: datetime
    target_end: datetime
    horizon_months: int | None
    model: str
    target_variable: str
    prediction: float | None
    unit: str | None
    scale: str | None
    alignment_status: str
    target_period_status: Literal["upcoming", "active", "ended", "invalid"]


class Assessment(Point):
    kind: Literal["forecast_assessment"] = "forecast_assessment"
    issued_at: datetime
    horizon_months: int
    forecast_version: int
    conflict_type: str
    probability_low: float | None
    probability_high: float | None
    confidence: str


T = TypeVar("T")


class Page(DashboardModel, Generic[T]):
    items: list[T]
    availability: Literal["available", "missing", "end_of_results"]
    limit: int
    offset: int
    next_offset: int | None


class CoverageEntry(DashboardModel):
    availability: Literal["available", "missing"]
    freshness: Literal["recent", "stale", "unknown"]
    latest_at: datetime | None
    latest_record_has_country_id: bool | None


class Coverage(DashboardModel):
    as_of: datetime
    stale_after_days: int
    country: str | None
    region: str | None
    observations: CoverageEntry
    ucdp_observations: CoverageEntry
    indicators: CoverageEntry
    predictions: CoverageEntry
    assessments: CoverageEntry


class Overview(DashboardModel):
    coverage: Coverage
    observation: Observation | None
    ucdp_observation: UCDPObservation | None
    indicator: IndicatorPoint | None
    prediction: Prediction | None
    assessment: Assessment | None


class RegionComparison(DashboardModel):
    region: str
    countries: list[Overview]
