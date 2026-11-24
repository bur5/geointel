"""Read-only adapters for existing persisted GEOINTEL records."""

from collections.abc import Iterable
from copy import deepcopy
from datetime import date

from geointel.domain.models import Event, Forecast, ForecastSignal
from geointel.domain.schemas import (
    NormalizedForecastSignal,
    NormalizedOperationalEvent,
    reject_boolean_prediction,
)
from geointel.early_warning import Observation, OperationalReceipt, TargetMapping, utc_day
from geointel.geography import resolve_country


def signal_observation(
    signal: ForecastSignal,
    *,
    mapping: TargetMapping,
    period_start: date,
    period_end: date,
) -> Observation:
    """Use the later of retrieval and local persistence for point-in-time availability."""
    if signal.id is None or signal.created_at is None:
        raise ValueError("a persisted external forecast signal is required")
    raw = (signal.provenance or {}).get("raw_adapter_record")
    if signal.provider == "VIEWS" and isinstance(raw, dict):
        reject_boolean_prediction(raw.get("prediction"))
    location = signal.source_location
    if signal.geographic_unit == "country":
        location = resolve_country(location).name
    utc_day(signal.retrieved_at)
    utc_day(signal.created_at)
    utc_day(signal.issue_date)
    if signal.retrieved_at < signal.issue_date:
        raise ValueError("external forecast retrieval precedes issuance")
    normalized = NormalizedForecastSignal(
        provider=signal.provider,
        source_record_id=signal.source_record_id,
        model_name=signal.model_name,
        model_version=signal.model_version,
        geographic_unit=signal.geographic_unit,
        location=location,
        issue_date=signal.issue_date,
        target_start=signal.target_start,
        target_end=signal.target_end,
        horizon_months=signal.horizon_months,
        target_variable=signal.target_variable,
        prediction=signal.prediction,
        unit=signal.unit,
        scale=signal.scale,
        alignment_status=signal.alignment_status,
        retrieved_at=max(signal.retrieved_at, signal.created_at),
    )
    return Observation.from_forecast(
        normalized, mapping=mapping, period_start=period_start, period_end=period_end
    )


def event_count_observation(events: Iterable[Event], *, receipt: OperationalReceipt) -> Observation:
    """Require explicit stored provenance and the identities from a coverage receipt."""
    normalized_events = []
    for event in events:
        provenance = event.provenance
        required = {
            "provider",
            "country",
            "source_record_id",
            "retrieved_at",
            "alignment_status",
            "temporal_classification",
        }
        if (
            event.id is None
            or event.occurred_at is None
            or event.created_at is None
            or not required.issubset(provenance)
        ):
            raise ValueError("stored event lacks operational provenance")
        normalized = NormalizedOperationalEvent.model_validate(provenance)
        utc_day(event.created_at)
        if (
            (str(event.source_record_id), event.event_type, event.occurred_at)
            != (normalized.source_record_id, normalized.event_type, normalized.event_date)
            or event.created_at > receipt.available_at
            or resolve_country(normalized.country).name != receipt.country
        ):
            raise ValueError("stored event disagrees with source provenance or receipt")
        normalized_events.append(normalized.model_copy(update={"country": receipt.country}))
    return Observation.from_events(normalized_events, receipt=receipt)


def forecast_context(forecast: Forecast, *, as_of: date) -> dict:
    """Represent a completed GEOINTEL assessment as context for a reader."""
    run = forecast.analysis_run
    if (
        forecast.id is None
        or run.status != "completed"
        or run.completed_at is None
        or forecast.created_at is None
        or max(utc_day(run.completed_at), utc_day(forecast.created_at)) > as_of
    ):
        raise ValueError("a completed assessment available by as_of is required")
    return {
        "forecast_id": str(forecast.id),
        "analysis_run_id": str(run.id),
        "conflict_type": forecast.conflict_type,
        "question": forecast.question,
        "horizon_months": forecast.horizon_months,
        "probability_low": forecast.probability_low,
        "probability_high": forecast.probability_high,
        "confidence": forecast.confidence,
        "unknowns": list(forecast.unknowns),
        "red_team": deepcopy(run.red_team_output),
    }
