from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from math import isfinite
from typing import Annotated, Generic, Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import Select, String, and_, cast, func, or_, select
from sqlalchemy.exc import InterfaceError, OperationalError, TimeoutError
from sqlalchemy.orm import Session, load_only
from sqlalchemy.sql.elements import ColumnElement

from geointel.api.dashboard_geography import (
    REGIONS,
    REVIEWED_GW_COUNTRIES,
    REVIEWED_ISO_GW,
    analysis_country_matches,
    geography,
    iso3,
    normalized,
    source_country_matches,
)
from geointel.api.dashboard_schemas import (
    Assessment,
    Coverage,
    CoverageEntry,
    Geography,
    IndicatorPoint,
    Observation,
    Overview,
    Page,
    Point,
    Prediction,
    Provenance,
    RegionComparison,
    UCDPObservation,
)
from geointel.domain.database import get_session
from geointel.domain.models import (
    AnalysisRun,
    Event,
    Evidence,
    Forecast,
    ForecastSignal,
    Indicator,
    Location,
    Source,
    utcnow,
)
from geointel.pipeline.historical import HISTORICAL_ROLES

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard v1"],
    responses={503: {"description": "Dashboard database unavailable"}},
)
DB = Annotated[Session, Depends(get_session)]
Region = Literal["eastern-asia", "southern-europe", "western-africa", "western-asia"]
STALE_AFTER_DAYS = 90
MAX_OFFSET = 10_000


@dataclass(frozen=True)
class Scope:
    country: str | None = None
    region: Region | None = None

    @property
    def countries(self) -> tuple[str, ...]:
        if self.country:
            return (self.country,)
        return REGIONS[self.region] if self.region else ()


def parse_country(country: str) -> str:
    code = iso3(country)
    if not code:
        raise HTTPException(422, "country must be an ISO 3166-1 alpha-2 or alpha-3 code")
    return code


def scope_filter(
    country: Annotated[str | None, Query(min_length=2, max_length=3)] = None,
    region: Region | None = None,
) -> Scope:
    code = parse_country(country) if country else None
    if code and region and code not in REGIONS[region]:
        raise HTTPException(422, "country is outside the supported cohort for this region")
    return Scope(code, region)


@dataclass(frozen=True)
class Window:
    start: date | None = None
    end: date | None = None
    limit: int = 50
    offset: int = 0


def window_filter(
    start: Annotated[date | None, Query(description="Inclusive UTC date")] = None,
    end: Annotated[date | None, Query(description="Exclusive UTC date")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> Window:
    if start and end and start >= end:
        raise HTTPException(422, "start must precede end")
    return Window(start, end, limit, offset)


ScopeFilter = Annotated[Scope, Depends(scope_filter)]
WindowFilter = Annotated[Window, Depends(window_filter)]


def utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def freshness(value: datetime | None, now: datetime) -> Literal["recent", "stale", "unknown"]:
    if value is None or value > now:
        return "unknown"
    return "stale" if now - value > timedelta(days=STALE_AFTER_DAYS) else "recent"


def finite(value: float | None) -> float | None:
    return value if value is not None and isfinite(value) else None


def metadata_string(data: dict, key: str) -> str | None:
    value = data.get(key)
    return value.strip() if isinstance(value, str) and value.strip() and len(value) <= 120 else None


def metadata_time(data: dict, key: str) -> datetime | None:
    value = metadata_string(data, key)
    if value:
        try:
            return utc(datetime.fromisoformat(value))
        except ValueError:
            pass
    return None


def point_fields(geo: Geography, timestamp: datetime | None, now: datetime):
    return {"geography": geo, "freshness": freshness(timestamp, now)}


def present_observation(row, now: datetime) -> Observation:
    event, name, code, provider = row
    metadata = event.provenance if isinstance(event.provenance, dict) else {}
    country = metadata_string(metadata, "country")
    event_geo = geography(country, None, "country") if country else geography(name, code, "country")
    occurred = utc(event.occurred_at)
    return Observation(
        id=event.id,
        occurred_at=occurred,
        event_type=event.event_type,
        reported_fatalities=nonnegative_int(metadata.get("fatalities")),
        temporal_classification=metadata_string(metadata, "temporal_classification"),
        confidence=event.confidence,
        provenance=Provenance(
            provider=provider,
            source_record_id=event.source_record_id,
            analysis_run_id=event.analysis_run_id,
            retrieved_at=metadata_time(metadata, "retrieved_at"),
        ),
        **point_fields(event_geo, occurred, now),
    )


def nonnegative_int(value) -> int | None:
    return value if type(value) is int and value >= 0 else None


def present_ucdp_observation(row, now: datetime) -> UCDPObservation:
    (evidence,) = row
    metadata = evidence.provenance
    fatalities = metadata.get("fatalities")
    fatalities = fatalities if isinstance(fatalities, dict) else {}
    occurred = utc(evidence.event_date)
    gw_code = nonnegative_int(metadata.get("country_id"))
    if gw_code is None:
        gw_code = nonnegative_int(metadata.get("resolved_ucdp_country_id"))
    country = metadata_string(metadata, "country") or REVIEWED_GW_COUNTRIES.get(gw_code)
    return UCDPObservation(
        id=evidence.id,
        occurred_at=occurred,
        ended_at=metadata_time(metadata, "date_end"),
        dataset=metadata_string(metadata, "dataset"),
        temporal_role=metadata["temporal_role"],
        coverage_end=metadata_time(metadata, "coverage_end"),
        violence_type_code=nonnegative_int(metadata.get("type_of_violence")),
        gw_country_code=gw_code,
        reported_fatalities_best=nonnegative_int(fatalities.get("best")),
        reported_fatalities_low=nonnegative_int(fatalities.get("low")),
        reported_fatalities_high=nonnegative_int(fatalities.get("high")),
        reliability=evidence.reliability,
        provenance=Provenance(
            provider="UCDP",
            source_record_id=evidence.source_record_id,
            analysis_run_id=evidence.analysis_run_id,
            version=metadata_string(metadata, "dataset_version"),
            retrieved_at=utc(evidence.retrieved_at),
        ),
        **point_fields(geography(country, None, "country"), occurred, now),
    )


def present_indicator(row, now: datetime) -> IndicatorPoint:
    indicator, name, code = row
    metadata = indicator.provenance if isinstance(indicator.provenance, dict) else {}
    observed = utc(indicator.observed_at)
    return IndicatorPoint(
        id=indicator.id,
        observed_at=observed,
        name=indicator.name,
        value=finite(indicator.value),
        unit=indicator.unit,
        provenance=Provenance(
            provider=metadata_string(metadata, "provider"),
            source_record_id=metadata_string(metadata, "record_id"),
            version=metadata_string(metadata, "dataset_version"),
            retrieved_at=metadata_time(metadata, "retrieved_at"),
        ),
        **point_fields(geography(name, code, "country"), observed, now),
    )


def target_period_status(start: datetime, end: datetime, now: datetime):
    if start > end:
        return "invalid"
    if now > end:
        return "ended"
    return "upcoming" if now < start else "active"


def present_prediction(row, now: datetime) -> Prediction:
    (signal,) = row
    issued = utc(signal.issue_date)
    start, end = utc(signal.target_start), utc(signal.target_end)
    return Prediction(
        id=signal.id,
        issued_at=issued,
        target_start=start,
        target_end=end,
        target_period_status=target_period_status(start, end, now),
        horizon_months=signal.horizon_months,
        model=signal.model_name,
        target_variable=signal.target_variable,
        prediction=finite(signal.prediction),
        unit=signal.unit,
        scale=signal.scale,
        alignment_status=signal.alignment_status,
        provenance=Provenance(
            provider=signal.provider,
            source_record_id=signal.source_record_id,
            analysis_run_id=signal.analysis_run_id,
            version=signal.model_version,
            retrieved_at=utc(signal.retrieved_at),
        ),
        **point_fields(
            geography(signal.source_location, None, signal.geographic_unit.strip().lower()),
            issued,
            now,
        ),
    )


def present_assessment(row, now: datetime) -> Assessment:
    forecast, name, code, version = row
    issued = utc(forecast.created_at)
    return Assessment(
        id=forecast.id,
        issued_at=issued,
        horizon_months=forecast.horizon_months,
        forecast_version=forecast.version,
        conflict_type=forecast.conflict_type,
        probability_low=finite(forecast.probability_low),
        probability_high=finite(forecast.probability_high),
        confidence=forecast.confidence,
        provenance=Provenance(
            provider="GEOINTEL", analysis_run_id=forecast.analysis_run_id, version=version
        ),
        **point_fields(geography(name, code, "country"), issued, now),
    )


PointType = TypeVar("PointType", bound=Point)


@dataclass(frozen=True)
class Series(Generic[PointType]):
    statement: Select
    date_column: ColumnElement
    id_column: ColumnElement
    present: Callable[..., PointType]
    country_matches: Callable[[str], ColumnElement]


def event_country_matches(code: str):
    country = Event.provenance["country"].as_string()
    return or_(
        source_country_matches(country, code),
        and_(or_(country.is_(None), normalized(country) == ""), analysis_country_matches(code)),
    )


def ucdp_country_matches(code: str):
    country = Evidence.provenance["country"].as_string()
    predicate = source_country_matches(country, code)
    gw_code = REVIEWED_ISO_GW.get(code)
    if gw_code is None:
        return predicate
    provider_code = func.coalesce(
        Evidence.provenance["country_id"].as_string(),
        Evidence.provenance["resolved_ucdp_country_id"].as_string(),
    )
    return or_(
        predicate,
        and_(
            or_(country.is_(None), normalized(country) == ""),
            cast(provider_code, String) == str(gw_code),
        ),
    )


OBSERVATIONS = Series(
    select(Event, Location.name, Location.iso_code, Source.name)
    .outerjoin(Location, Event.location_id == Location.id)
    .outerjoin(Source, Event.source_id == Source.id)
    .options(
        load_only(
            Event.id,
            Event.occurred_at,
            Event.event_type,
            Event.confidence,
            Event.source_record_id,
            Event.analysis_run_id,
            Event.provenance,
        )
    ),
    Event.occurred_at,
    Event.id,
    present_observation,
    event_country_matches,
)
UCDP_OBSERVATIONS = Series(
    select(Evidence)
    .join(Source, Evidence.source_id == Source.id)
    .where(
        Source.name == "UCDP",
        Evidence.provenance["temporal_role"]
        .as_string()
        .in_(sorted(HISTORICAL_ROLES | {"candidate_recent"})),
    )
    .options(
        load_only(
            Evidence.id,
            Evidence.event_date,
            Evidence.source_record_id,
            Evidence.analysis_run_id,
            Evidence.retrieved_at,
            Evidence.reliability,
            Evidence.provenance,
        )
    ),
    Evidence.event_date,
    Evidence.id,
    present_ucdp_observation,
    ucdp_country_matches,
)
INDICATORS = Series(
    select(Indicator, Location.name, Location.iso_code).outerjoin(
        Location, Indicator.location_id == Location.id
    ),
    Indicator.observed_at,
    Indicator.id,
    present_indicator,
    analysis_country_matches,
)
PREDICTIONS = Series(
    select(ForecastSignal).options(
        load_only(
            ForecastSignal.id,
            ForecastSignal.issue_date,
            ForecastSignal.target_start,
            ForecastSignal.target_end,
            ForecastSignal.horizon_months,
            ForecastSignal.model_name,
            ForecastSignal.target_variable,
            ForecastSignal.prediction,
            ForecastSignal.unit,
            ForecastSignal.scale,
            ForecastSignal.alignment_status,
            ForecastSignal.provider,
            ForecastSignal.source_record_id,
            ForecastSignal.analysis_run_id,
            ForecastSignal.model_version,
            ForecastSignal.retrieved_at,
            ForecastSignal.source_location,
            ForecastSignal.geographic_unit,
        )
    ),
    ForecastSignal.issue_date,
    ForecastSignal.id,
    present_prediction,
    lambda code: and_(
        normalized(ForecastSignal.geographic_unit) == "country",
        source_country_matches(ForecastSignal.source_location, code),
    ),
)
ASSESSMENTS = Series(
    select(Forecast, Location.name, Location.iso_code, AnalysisRun.pipeline_version)
    .join(AnalysisRun, Forecast.analysis_run_id == AnalysisRun.id)
    .join(Location, AnalysisRun.location_id == Location.id)
    .where(AnalysisRun.status == "completed")
    .options(
        load_only(
            Forecast.id,
            Forecast.created_at,
            Forecast.analysis_run_id,
            Forecast.horizon_months,
            Forecast.version,
            Forecast.conflict_type,
            Forecast.probability_low,
            Forecast.probability_high,
            Forecast.confidence,
        )
    ),
    Forecast.created_at,
    Forecast.id,
    present_assessment,
    analysis_country_matches,
)


def read_series(session: Session, series: Series, scope: Scope, window: Window):
    statement = series.statement
    if scope.countries:
        statement = statement.where(
            or_(*(series.country_matches(code) for code in scope.countries))
        )
    if window.start:
        statement = statement.where(
            series.date_column >= datetime.combine(window.start, time(), UTC)
        )
    if window.end:
        statement = statement.where(series.date_column < datetime.combine(window.end, time(), UTC))
    statement = (
        statement.order_by(series.date_column.desc().nulls_last(), series.id_column.asc())
        .limit(window.limit + 1)
        .offset(window.offset)
    )
    try:
        rows = session.execute(statement).all()
    except (OperationalError, InterfaceError, TimeoutError):
        raise HTTPException(503, "Dashboard database unavailable") from None
    return rows


def page(
    session: Session, series: Series[PointType], scope: Scope, window: Window
) -> Page[PointType]:
    now = utcnow()
    rows = read_series(session, series, scope, window)
    next_offset = window.offset + window.limit
    return Page(
        items=[series.present(row, now) for row in rows[: window.limit]],
        availability="available" if rows else "end_of_results" if window.offset else "missing",
        limit=window.limit,
        offset=window.offset,
        next_offset=next_offset if len(rows) > window.limit and next_offset <= MAX_OFFSET else None,
    )


def coverage_entry(point: Point | None, timestamp: datetime | None) -> CoverageEntry:
    return CoverageEntry(
        availability="available" if point else "missing",
        freshness=point.freshness if point else "unknown",
        latest_at=timestamp,
        latest_record_has_country_id=point.geography.iso3 is not None if point else None,
    )


def overview(session: Session, scope: Scope, now: datetime) -> Overview:
    def latest(series: Series[PointType]) -> PointType | None:
        rows = read_series(session, series, scope, Window(limit=1))
        return series.present(rows[0], now) if rows else None

    observation = latest(OBSERVATIONS)
    ucdp = latest(UCDP_OBSERVATIONS)
    indicator = latest(INDICATORS)
    prediction = latest(PREDICTIONS)
    assessment = latest(ASSESSMENTS)
    return Overview(
        coverage=Coverage(
            as_of=now,
            stale_after_days=STALE_AFTER_DAYS,
            country=scope.country,
            region=scope.region,
            observations=coverage_entry(
                observation, observation.occurred_at if observation else None
            ),
            ucdp_observations=coverage_entry(ucdp, ucdp.occurred_at if ucdp else None),
            indicators=coverage_entry(indicator, indicator.observed_at if indicator else None),
            predictions=coverage_entry(prediction, prediction.issued_at if prediction else None),
            assessments=coverage_entry(assessment, assessment.issued_at if assessment else None),
        ),
        observation=observation,
        ucdp_observation=ucdp,
        indicator=indicator,
        prediction=prediction,
        assessment=assessment,
    )


@router.get("/overview", response_model=Overview)
def get_overview(session: DB, scope: ScopeFilter):
    """Latest stored point and coverage for each series, globally or within a filter."""
    return overview(session, scope, utcnow())


@router.get("/countries/{country}", response_model=Overview)
def get_country(session: DB, country: Annotated[str, Path(min_length=2, max_length=3)]):
    """Latest records for a single ISO country."""
    return overview(session, Scope(country=parse_country(country)), utcnow())


@router.get("/regions/{region}", response_model=RegionComparison)
def get_region(session: DB, region: Region):
    """Show the region's supported countries side by side."""
    now = utcnow()
    return RegionComparison(
        region=region,
        countries=[overview(session, Scope(code, region), now) for code in REGIONS[region]],
    )


@router.get("/coverage", response_model=Coverage)
def get_coverage(session: DB, scope: ScopeFilter):
    """Report latest record availability and age for each series."""
    return overview(session, scope, utcnow()).coverage


@router.get("/observations", response_model=Page[Observation])
def get_observations(session: DB, scope: ScopeFilter, window: WindowFilter):
    """Stored reported events. Date filters apply to event occurrence."""
    return page(session, OBSERVATIONS, scope, window)


@router.get("/ucdp-observations", response_model=Page[UCDPObservation])
def get_ucdp_observations(session: DB, scope: ScopeFilter, window: WindowFilter):
    """Stored UCDP GED and Candidate observations. Filter by occurrence start."""
    return page(session, UCDP_OBSERVATIONS, scope, window)


@router.get("/indicators", response_model=Page[IndicatorPoint])
def get_indicators(session: DB, scope: ScopeFilter, window: WindowFilter):
    """Stored indicator points. Date filters apply to observation dates."""
    return page(session, INDICATORS, scope, window)


@router.get("/forecasts", response_model=Page[Prediction])
def get_predictions(session: DB, scope: ScopeFilter, window: WindowFilter):
    """External model forecast points in native units. Date filters apply to issuance."""
    return page(session, PREDICTIONS, scope, window)


@router.get("/assessments", response_model=Page[Assessment])
def get_assessments(session: DB, scope: ScopeFilter, window: WindowFilter):
    """Completed GEOINTEL assessments. Date filters apply to issuance."""
    return page(session, ASSESSMENTS, scope, window)
