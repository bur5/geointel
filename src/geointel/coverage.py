"""Versioned provider retrieval and assessment decisions."""

from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from geointel.domain.schemas import (
    NormalizedForecastSignal,
    NormalizedNewsReport,
    NormalizedOperationalEvent,
)
from geointel.geography import resolve_country


class CoverageState(StrEnum):
    UNKNOWN = "unknown"
    NOT_ATTEMPTED = "not_attempted"
    FAILED = "failed"
    PARTIAL = "partial"
    COMPLETE_WITH_RECORDS = "complete_with_records"
    COMPLETE_EMPTY = "complete_empty"


ScopeKind = Literal["events", "historical_release", "forecast", "media", "unspecified"]
CONNECTOR_KINDS: dict[str, ScopeKind] = {
    "ACLED": "events",
    "UCDP": "historical_release",
    "CAST": "forecast",
    "VIEWS": "forecast",
    "NEWSAPI": "media",
    "GDELT": "media",
}


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ScopeKind
    geography: str
    start: date | None = None
    end: date | None = None
    horizon_months: int | None = Field(default=None, ge=1)
    release: str | None = None


class Verification(BaseModel):
    """Assertion issued by a reviewed connector for this invocation."""

    scope: Scope
    basis: str = Field(min_length=1)
    pagination_exhausted: Literal[True]


Check = Literal["pass", "fail", "unknown", "not_applicable"]


class RecordDecision(BaseModel):
    kind: Literal["event", "forecast", "media"]
    provider: str
    record_id: str
    geography: Check
    observation_time: Check = "not_applicable"
    publication_freshness: Check = "not_applicable"
    forecast_issuance: Check = "not_applicable"
    forecast_target: Check = "not_applicable"
    eligible: bool


class EventCounts(BaseModel):
    retrieved: int | None = None
    rejected: int | None = None
    duplicate: int = 0
    eligible: int = 0
    confirmed: Literal[0] | None = None


class CollectionDecision(BaseModel):
    collection_id: str
    connector: str
    state: CoverageState
    requested_geography: str
    requested_scope: Scope
    actual_query_scope: Scope | None = None
    verified_scope: Scope | None = None
    gaps: list[str]
    provider_release: str | None = None
    provider_versions: list[str]
    retrieval_evidence: dict[str, Any] | None = None
    error_causes: list[str]
    event_counts: EventCounts
    records: list[RecordDecision]

    @model_validator(mode="after")
    def validate_zero(self):
        if self.event_counts.confirmed == 0 and (
            self.state != CoverageState.COMPLETE_EMPTY
            or self.requested_scope.kind != "events"
            or self.verified_scope != self.requested_scope
            or self.actual_query_scope != self.requested_scope
            or self.event_counts.retrieved != 0
        ):
            raise ValueError("confirmed zero requires verified exact empty event scope")
        return self


class CoverageDecision(BaseModel):
    version: Literal[1] = 1
    evaluated_at: datetime | None = None
    collections: list[CollectionDecision] = Field(default_factory=list)

    @classmethod
    def from_metadata(cls, metadata: dict) -> "CoverageDecision":
        raw = metadata.get("collection_coverage")
        if not isinstance(raw, dict) or type(raw.get("version")) is not int or raw["version"] != 1:
            return cls()
        try:
            result = cls.model_validate(raw)
        except ValidationError:
            return cls()
        identities = {item.collection_id for item in result.collections}
        return result if len(identities) == len(result.collections) else cls()

    def eligibility(self) -> dict[tuple[str, str, str], bool]:
        decisions = {}
        for entry in self.collections:
            for record in entry.records:
                decisions.setdefault(
                    (record.kind, record.provider, record.record_id), record.eligible
                )
        return decisions

    def projection(self, connector: str | None = None) -> dict:
        entries = [item for item in self.collections if connector in (None, item.connector)]
        return {
            "version": self.version,
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
            "state": entries[0].state.value if len(entries) == 1 else "unknown",
            "collections": [item.model_dump(mode="json") for item in entries],
        }


def _country(value):
    try:
        return resolve_country(value).name if isinstance(value, str) else None
    except ValueError:
        return None


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def assess_record(
    record: NormalizedOperationalEvent | NormalizedForecastSignal | NormalizedNewsReport,
    location: str,
    as_of: datetime,
    horizon_months: int,
) -> RecordDecision:
    requested = _country(location)
    if isinstance(record, NormalizedNewsReport):
        publication = record.publication_timestamp
        if publication is None:
            freshness = "unknown"
        else:
            published = _utc(publication)
            retrieved = _utc(record.retrieval_timestamp)
            freshness = (
                "pass" if as_of - timedelta(days=90) <= published <= retrieved <= as_of else "fail"
            )
        return RecordDecision(
            kind="media",
            provider=record.provider,
            record_id=record.source_record_id,
            geography="unknown",
            publication_freshness=freshness,
            eligible=False,
        )

    is_event = isinstance(record, NormalizedOperationalEvent)
    if isinstance(record, NormalizedOperationalEvent):
        actual = _country(record.country)
    else:
        actual = (
            _country(record.location) if record.geographic_unit.casefold() == "country" else None
        )
    geography = (
        "unknown" if not requested or not actual else ("pass" if requested == actual else "fail")
    )
    if any("geographic mismatch" in note.casefold() for note in record.alignment_notes):
        geography = "fail"
    retrieved = _utc(record.retrieved_at)
    checks: dict[str, Check] = {}
    if isinstance(record, NormalizedOperationalEvent):
        observed = _utc(record.event_date)
        checks["observation_time"] = (
            "pass"
            if as_of.date() - timedelta(days=90) <= observed.date()
            and observed <= retrieved <= as_of
            else "fail"
        )
        # Provider update time is distinct from occurrence and original publication.
        checks["publication_freshness"] = "unknown"
        valid_value = bool(record.event_type.strip())
    else:
        issued = _utc(record.issue_date)
        checks["forecast_issuance"] = (
            "pass"
            if issued <= retrieved <= as_of and as_of - issued <= timedelta(days=45)
            else "fail"
        )
        start, end = _utc(record.target_start), _utc(record.target_end)
        years, month = divmod(as_of.month - 1 + horizon_months, 12)
        year = as_of.year + years
        horizon_end = as_of.replace(
            year=year, month=month + 1, day=min(as_of.day, monthrange(year, month + 1)[1])
        )
        checks["forecast_target"] = (
            "pass" if issued <= start <= end and as_of <= end and start <= horizon_end else "fail"
        )
        valid_value = isfinite(record.prediction) and bool(record.target_variable.strip())
    return RecordDecision(
        kind="event" if is_event else "forecast",
        provider=record.provider,
        record_id=record.source_record_id,
        geography=geography,
        **checks,
        eligible=bool(
            record.source_record_id.strip()
            and geography == "pass"
            and all(
                value == "pass" for key, value in checks.items() if key != "publication_freshness"
            )
            and valid_value
        ),
    )


def decide_collection(
    *,
    collection_id: str,
    connector: str,
    location: str,
    horizon_months: int,
    evaluated_at: datetime,
    outcome: dict[str, Any],
    received: list,
    unique: list,
    already_seen: set[tuple[str, str]],
    adapter_query_scope: Scope | None = None,
) -> CollectionDecision:
    audit = outcome.get("collection_audit") or {}
    try:
        actual = (
            Scope.model_validate(audit.get("query_scope"))
            if audit.get("query_scope")
            else adapter_query_scope
        )
    except ValidationError:
        actual = None
    kind = CONNECTOR_KINDS.get(connector, "unspecified")
    requested = Scope(
        kind=kind,
        geography=_country(location) or location,
        start=evaluated_at.date() - timedelta(days=90) if kind == "events" else None,
        end=evaluated_at.date() if kind == "events" else None,
        horizon_months=horizon_months if kind == "forecast" else None,
        release=actual.release if kind == "historical_release" and actual else None,
    )
    errors = list(
        dict.fromkeys(
            str(value)
            for value in (
                outcome.get("failure_category"),
                outcome.get("failure_reason"),
                audit.get("failure_category"),
                audit.get("failure_reason"),
                *audit.get("rejection_reasons", []),
            )
            if value
        )
    )
    records = [
        assess_record(item, location, evaluated_at, horizon_months)
        for item in unique
        if isinstance(
            item, (NormalizedOperationalEvent, NormalizedForecastSignal, NormalizedNewsReport)
        )
    ]
    restriction = audit.get("coverage_restricted") or outcome.get("status") == "recency_restricted"
    incomplete = (
        audit.get("status") == "PARTIAL"
        or audit.get("truncated")
        or audit.get("rejected")
        or audit.get("rate_limited")
        or restriction
    )
    gaps = []
    if restriction:
        gaps.append("provider_restriction")
    if incomplete:
        gaps.append("incomplete_retrieval")
    verified = None
    if not outcome["attempted"]:
        state = CoverageState.NOT_ATTEMPTED
    elif outcome["status"] == "failed" or audit.get("status") == "FAILED":
        state = CoverageState.PARTIAL if unique else CoverageState.FAILED
    elif incomplete:
        state = CoverageState.PARTIAL
    else:
        proof = audit.get("verification")
        try:
            verification = Verification.model_validate(proof) if proof else None
        except ValidationError:
            verification = None
        received_count = audit.get("received")
        if (
            verification
            and actual is not None
            and actual == verification.scope
            and audit.get("status") == "SUCCEEDED"
            and audit.get("page_count", 0) > 0
            and len(audit.get("page_evidence", [])) == audit["page_count"]
            and type(received_count) is int
            and received_count >= 0
            and audit.get("accepted") == len(received)
            and not audit.get("pagination_ambiguous")
            and not errors
            and received_count == len(received) + audit.get("duplicates", 0)
            and _country(actual.geography) == actual.geography
        ):
            verified = verification.scope
            state = (
                CoverageState.COMPLETE_WITH_RECORDS
                if received_count
                else (CoverageState.COMPLETE_EMPTY)
            )
        else:
            state = CoverageState.UNKNOWN
    if audit.get("pagination_ambiguous"):
        gaps.append("pagination_unverified")
    if state == CoverageState.FAILED:
        gaps.append("retrieval_failed")
    if verified != requested:
        gaps.append("assessment_scope_unverified")
    event_received = sum(isinstance(item, NormalizedOperationalEvent) for item in received)
    event_unique = [item for item in records if item.kind == "event"]
    event_audit = kind in {"events", "historical_release"} and bool(audit)
    event_duplicates = audit.get("duplicates", 0) if event_audit else 0
    cross_duplicates = sum((item.provider, item.record_id) in already_seen for item in event_unique)
    eligible = sum(item.eligible for item in event_unique)
    confirmed: Literal[0] | None = None
    if kind == "events" and verified == requested and state == CoverageState.COMPLETE_EMPTY:
        confirmed = 0
    versions = sorted(
        {
            item.model_version
            for item in unique
            if isinstance(item, NormalizedForecastSignal) and item.model_version
        }
    )
    return CollectionDecision(
        collection_id=collection_id,
        connector=connector,
        state=state,
        requested_geography=location,
        requested_scope=requested,
        actual_query_scope=actual,
        verified_scope=verified,
        gaps=gaps,
        provider_release=actual.release if actual else None,
        provider_versions=versions,
        retrieval_evidence=audit or None,
        error_causes=errors,
        event_counts=EventCounts(
            retrieved=audit.get("received")
            if event_audit
            else (event_received if received else None),
            rejected=audit.get("rejected") if event_audit else None,
            duplicate=event_duplicates + event_received - len(event_unique) + cross_duplicates,
            eligible=eligible,
            confirmed=confirmed,
        ),
        records=records,
    )
