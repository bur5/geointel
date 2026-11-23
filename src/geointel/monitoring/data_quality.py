"""Read-only health diagnostics for a persisted analysis snapshot."""

from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from math import isfinite
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from geointel.domain.models import AnalysisRun, Event, Source
from geointel.geography import resolve_country

DEFAULT_FRESHNESS_DAYS = {"ACLED": 14, "VIEWS": 45, "CAST": 45, "ForecastSignal": 45}
STATUS_PRIORITY = ("healthy", "degraded", "stale", "unavailable")


def _timestamp(value):
    if isinstance(value, str):
        if len(value) <= 10:
            return None
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    # SQLite returns naive datetimes for the application's UTC columns.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _geography(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return resolve_country(value).name.casefold()
    except ValueError:
        return " ".join(value.casefold().split())


def _signal_country(row):
    unit = _geography(row.geographic_unit)
    if unit == "country":
        return row.source_location
    if (
        row.provider == "CAST"
        and unit == "admin1"
        and row.provenance.get("schema") == "geointel-cast-official-v1"
    ):
        # Official CAST IDs use country|admin1|year|month|target.
        country, admin, *_ = (row.source_record_id or "").split("|") + [""]
        if _geography(admin) == _geography(row.source_location) and admin:
            return country
    return None


def _inspect_record(row, run, as_of, findings):
    if isinstance(row, Event):
        geography = _geography(row.provenance.get("country"))
        observed = _timestamp(row.occurred_at)
        retrieved = _timestamp(row.provenance.get("retrieved_at"))
        valid_time = observed and retrieved and observed <= retrieved <= as_of
        expired = False
        valid_value = bool(row.event_type and row.event_type.strip())
    else:
        geography = _geography(_signal_country(row))
        observed = _timestamp(row.issue_date)
        retrieved = _timestamp(row.retrieved_at)
        start = _timestamp(row.target_start)
        end = _timestamp(row.target_end)
        valid_time = (
            observed
            and retrieved
            and start
            and end
            and observed <= retrieved <= as_of
            and start <= end
        )
        expired = bool(valid_time and end < as_of)
        valid_value = (
            isinstance(row.prediction, (int, float))
            and isfinite(row.prediction)
            and bool(row.target_variable and row.target_variable.strip())
        )

    valid_geo = (
        geography is not None
        and geography == _geography(run.location.name)
        and row.location_id == run.location_id
    )
    if not valid_geo:
        findings["geography_mismatch" if geography else "missing_geography"] += 1
    if not valid_time:
        findings["invalid_timestamp"] += 1
    if not valid_value:
        findings["missing_or_invalid_value"] += 1
    if not row.source_record_id or not row.source_record_id.strip():
        findings["missing_record_id"] += 1
        return None, False
    return (observed, expired) if valid_geo and valid_time and valid_value else (None, False)


def _count(value, findings):
    if type(value) is not int or value < 0:
        findings["invalid_collection_metadata"] += 1
        return 0
    return value


def _collection_findings(outcomes, row_count, as_of, findings):
    if len(outcomes) != 1:
        findings["missing_outcome" if not outcomes else "ambiguous_outcome"] += 1
        return False

    outcome = outcomes[0]
    available = outcome.get("status") == "succeeded" and outcome.get("succeeded") is True
    if not available:
        findings["collection_unavailable"] += 1
    if _count(outcome.get("record_count"), findings) != row_count:
        findings["record_count_mismatch"] += 1
    collected = _timestamp(outcome.get("collection_timestamp"))
    if collected is None or collected > as_of:
        findings["invalid_collection_timestamp"] += 1
    findings["duplicate_records"] += _count(outcome.get("duplicates_removed", 0), findings)
    audit = outcome.get("collection_audit")
    if audit is None:
        return available
    if not isinstance(audit, dict):
        findings["invalid_collection_metadata"] += 1
        return False
    findings["duplicate_records"] += _count(audit.get("duplicates"), findings)
    findings["rejected_records"] += _count(audit.get("rejected"), findings)
    if (
        audit.get("status") == "PARTIAL"
        or audit.get("truncated")
        or audit.get("failure_category")
        or audit.get("rate_limited")
    ):
        findings["incomplete_collection"] += 1
    if audit.get("status") not in {"SUCCEEDED", "PARTIAL"}:
        findings["collection_audit_unavailable"] += 1
        return False
    return available


def _inspect_rows(rows, run, as_of, days, findings):
    identities = Counter(
        ("ACLED" if isinstance(row, Event) else row.provider, row.source_record_id)
        for row in rows
        if row.source_record_id and row.source_record_id.strip()
    )
    findings["duplicate_records"] += sum(count - 1 for count in identities.values())
    timestamps = []
    expired_timestamps = []
    for row in rows:
        timestamp, expired = _inspect_record(row, run, as_of, findings)
        if timestamp is not None:
            (expired_timestamps if expired else timestamps).append(timestamp)
    current_count = len(timestamps)
    expired_count = len(expired_timestamps)
    timestamps = timestamps or expired_timestamps
    latest = max(timestamps, default=None)
    age = (as_of - latest).total_seconds() if latest is not None else None
    old_count = sum(as_of - timestamp > timedelta(days=days) for timestamp in timestamps)
    if latest is None:
        findings["missing_usable_records"] += 1
    elif old_count == len(timestamps):
        findings["stale_observations"] += old_count
    if expired_count and not current_count:
        findings["expired_target_coverage"] += expired_count
    return {
        "latest_at": latest.isoformat() if latest is not None else None,
        "age_seconds": age,
        "threshold_days": days,
        "stale_record_count": old_count,
    }, {
        "record_count": len(rows),
        "usable_record_count": current_count + expired_count,
        "expired_target_count": expired_count,
        "unique_record_id_count": len(identities),
    }


def _report(rows, run, as_of, days, outcomes=None):
    findings = Counter()
    available = outcomes is None or _collection_findings(outcomes, len(rows), as_of, findings)
    freshness, coverage = _inspect_rows(rows, run, as_of, days, findings)
    if not available or not coverage["usable_record_count"]:
        status = "unavailable"
    elif findings["stale_observations"] or findings["expired_target_coverage"]:
        status = "stale"
    else:
        status = "degraded" if +findings else "healthy"
    return {
        "status": status,
        "freshness": freshness,
        "coverage": coverage,
        "findings": [{"code": code, "count": count} for code, count in sorted((+findings).items())],
    }


def _thresholds(overrides):
    result = DEFAULT_FRESHNESS_DAYS | dict(overrides or {})
    if result.keys() != DEFAULT_FRESHNESS_DAYS.keys() or any(
        type(days) is not int or not 1 <= days <= timedelta.max.days for days in result.values()
    ):
        raise ValueError("freshness overrides require known sources and positive whole days")
    return result


def source_health_report(
    session: Session,
    analysis_run_id: UUID,
    *,
    as_of: datetime,
    freshness_days: Mapping[str, int] | None = None,
) -> dict:
    """Inspect one completed run. Invalid requests and database errors propagate."""
    thresholds = _thresholds(freshness_days)
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware datetime")
    as_of = as_of.astimezone(UTC)
    with session.no_autoflush:
        run = session.get(AnalysisRun, analysis_run_id)
        if run is None or run.status != "completed":
            raise ValueError("a completed analysis run is required")
        if (completed := _timestamp(run.completed_at)) is None or completed > as_of:
            raise ValueError("analysis run must have completed by as_of")
        geography = run.location.name
        events = session.scalars(
            select(Event)
            .join(Source, Source.id == Event.source_id)
            .where(Event.analysis_run_id == analysis_run_id, Source.name == "ACLED")
        ).all()
        signals = list(run.forecast_signals)
        metadata = run.collection_metadata.get("connector_outcomes", [])
        if not isinstance(metadata, list) or any(not isinstance(item, dict) for item in metadata):
            raise ValueError("malformed connector outcomes")
        outcomes = {}
        for item in metadata:
            outcomes.setdefault(item.get("connector"), []).append(item)

        acled = _report(events, run, as_of, thresholds["ACLED"], outcomes.get("ACLED", []))
        reports = {}
        providers = sorted({"VIEWS", "CAST", *(row.provider for row in signals)})
        for provider in providers:
            reports[provider] = _report(
                [row for row in signals if row.provider == provider],
                run,
                as_of,
                thresholds[provider]
                if provider in {"CAST", "VIEWS"}
                else thresholds["ForecastSignal"],
                outcomes.get(provider, []),
            )

    # Aggregate identities are provider-scoped. Use provider reports for duplicate checks
    # and to prevent one healthy provider from masking another provider's issues.
    aggregate = _report(signals, run, as_of, thresholds["ForecastSignal"])
    aggregate["provider_statuses"] = {name: reports[name]["status"] for name in providers}
    statuses = [reports[name]["status"] for name in providers]
    if (
        signals
        and "unavailable" in statuses
        and any(status != "unavailable" for status in statuses)
    ):
        statuses = ["degraded" if status == "unavailable" else status for status in statuses]
    unhealthy = sum(report["status"] != "healthy" for report in reports.values())
    if unhealthy:
        aggregate["findings"].append({"code": "unhealthy_signal_providers", "count": unhealthy})
    aggregate["status"] = max([aggregate["status"], *statuses], key=STATUS_PRIORITY.index)

    return {
        "schema_version": 1,
        "report_type": "source_data_quality",
        "analysis_run_id": str(analysis_run_id),
        "as_of": as_of.isoformat(),
        "geography": geography,
        "sources": {
            "ACLED": acled,
            "VIEWS": reports["VIEWS"],
            "CAST": reports["CAST"],
            "ForecastSignal": aggregate,
        },
        "other_signal_providers": {
            name: reports[name] for name in providers if name not in {"VIEWS", "CAST"}
        },
    }
