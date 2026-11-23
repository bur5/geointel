"""Read-only mappings from GEOINTEL's existing records to warning observations."""

from collections.abc import Iterable
from datetime import date, timedelta

from geointel.domain.models import Event, Forecast, ForecastSignal
from geointel.early_warning import Kind, Observation, Region, Stream
from geointel.geography import resolve_country


def forecast_observation(forecast: Forecast, *, model: str) -> Observation:
    """Use the midpoint of a stored interval after the caller verifies comparable runs."""
    run = forecast.analysis_run
    if forecast.id is None or run.status != "completed" or run.completed_at is None:
        raise ValueError("Expected a stored forecast from a completed analysis run")
    low, high = forecast.probability_low, forecast.probability_high
    value = (
        (low + high) / 2 if low is not None and high is not None and 0 <= low <= high <= 1 else None
    )
    day = run.completed_at.date()
    return Observation(
        Region("country", resolve_country(run.location.name).name),
        forecast.conflict_type,
        Stream(Kind.PROBABILITY, "GEOINTEL", model),
        day,
        max(day, forecast.created_at.date()),
        value,
        str(forecast.id),
        forecast.horizon_months,
    )


def signal_observation(signal: ForecastSignal, *, model: str) -> Observation:
    """Accept explicitly declared probability fractions from reviewed provider mappings."""
    if signal.unit != "probability" or signal.scale != "0-1":
        raise ValueError("Forecast signal must declare a 0–1 probability")
    if signal.alignment_status != "aligned":
        raise ValueError("Forecast signal failed upstream alignment")
    region = (
        resolve_country(signal.source_location).name
        if signal.geographic_unit == "country"
        else signal.source_location
    )
    return Observation(
        Region(signal.geographic_unit, region),
        signal.target_variable,
        Stream(Kind.PROBABILITY, signal.provider, model),
        signal.issue_date.date(),
        max(signal.retrieved_at.date(), signal.created_at.date()),
        signal.prediction,
        signal.source_record_id,
        signal.horizon_months,
        (signal.target_start.date(), signal.target_end.date()),
    )


def event_count_observation(
    events: Iterable[Event],
    *,
    region: Region,
    target: str,
    series: str,
    event_types: frozenset[str],
    period_end: date,
    cadence_days: int,
    available_on: date,
    coverage_record_id: str,
) -> Observation:
    """Summarize one externally verified, complete ACLED country coverage window."""
    if region.unit != "country" or cadence_days < 1 or not coverage_record_id or not event_types:
        raise ValueError("Expected verified country coverage and a nonempty event type filter")
    start = period_end - timedelta(days=cadence_days - 1)
    ids = set()
    for event in events:
        provenance = event.provenance
        if (
            provenance.get("provider") != "ACLED"
            or provenance.get("alignment_status") != "aligned"
            or resolve_country(provenance.get("country", "")).name != region.identifier
            or not event.source_record_id
            or event.occurred_at is None
            or not start <= event.occurred_at.date() <= period_end
            or event.created_at.date() > available_on
        ):
            raise ValueError("Event does not match the declared coverage window")
        if event.event_type in event_types:
            ids.add(event.source_record_id)
    return Observation(
        region,
        target,
        Stream(Kind.EVENTS, "ACLED", series),
        period_end,
        available_on,
        len(ids),
        coverage_record_id,
    )
