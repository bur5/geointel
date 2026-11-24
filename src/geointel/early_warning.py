"""Deterministic, advisory evaluation of comparable geopolitical risk observations."""

from calendar import monthrange
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from itertools import pairwise
from json import dumps
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from geointel.domain.schemas import (
    NormalizedForecastSignal,
    NormalizedOperationalEvent,
    reject_boolean_prediction,
)


class Level(StrEnum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


_SEVERITY = (Level.NORMAL, Level.WATCH, Level.WARNING, Level.CRITICAL)


class _Record(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
        revalidate_instances="always",
    )


class Feed(_Record):
    provider: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    model: str | None = Field(default=None, min_length=1)
    version: str | None = Field(default=None, min_length=1)


def _feed_key(feed: Feed) -> tuple[str, str, str, str]:
    return feed.provider, feed.metric, feed.model or "", feed.version or ""


class Thresholds(_Record):
    cadence_days: int = Field(default=7, ge=1)
    minimum_observations: int = Field(default=3, ge=3)
    maximum_age_days: int = Field(default=10, ge=0)
    recovery_observations: int = Field(default=2, ge=2)
    probability_jump: float = Field(default=0.15, gt=0, le=1)
    trend_step: float = Field(default=0.025, gt=0, le=1)
    trend_total: float = Field(default=0.10, gt=0, le=1)
    disagreement: float = Field(default=0.25, gt=0, le=1)
    low_baseline: float = Field(default=0.10, ge=0, lt=1)
    emerging_current: float = Field(default=0.20, gt=0, le=1)
    activity_increase: int = Field(default=5, ge=2)
    activity_trend_step: int = Field(default=2, ge=1)
    activity_ratio: float = Field(default=2, gt=1)

    @model_validator(mode="after")
    def emerging_order(self):
        if self.low_baseline >= self.emerging_current:
            raise ValueError("emerging_current must exceed low_baseline")
        return self


def utc_day(timestamp: datetime) -> date:
    if timestamp.utcoffset() is None:
        raise ValueError("source timestamps require a timezone")
    return timestamp.astimezone(UTC).date()


class TargetMapping(_Record):
    mapping_id: str = Field(min_length=1)
    feed: Feed
    source_target: str = Field(min_length=1)
    geographic_unit: str = Field(min_length=1)
    horizon_months: int = Field(ge=1)
    start_month_offset: int = Field(ge=1)

    @model_validator(mode="after")
    def require_forecast_feed(self):
        if self.feed.model is None or self.feed.version is None:
            raise ValueError("target mappings require a versioned forecast model")
        return self

    def window(self, issued: date) -> tuple[date, date]:
        start_month = issued.year * 12 + issued.month - 1 + self.start_month_offset
        end_month = start_month + self.horizon_months - 1
        start_year, start_index = divmod(start_month, 12)
        end_year, end_index = divmod(end_month, 12)
        return (
            date(start_year, start_index + 1, 1),
            date(end_year, end_index + 1, monthrange(end_year, end_index + 1)[1]),
        )


class ActivityMapping(_Record):
    feed: Feed
    target: str = Field(min_length=1)
    version: str = Field(min_length=1)
    review_ref: str = Field(min_length=1)


class Scope(_Record):
    region: str = Field(min_length=1)
    geographic_unit: str = Field(min_length=1)
    horizon_months: int | None = Field(default=None, ge=1)
    feeds: tuple[Feed, ...] = Field(min_length=1)
    target_mappings: tuple[TargetMapping, ...] = ()
    activity_mappings: tuple[ActivityMapping, ...] = ()

    @model_validator(mode="after")
    def comparable_feeds(self):
        forecasts = [feed for feed in self.feeds if feed.model is not None]
        if len(set(self.feeds)) != len(self.feeds):
            raise ValueError("feeds must be unique")
        if forecasts and (self.horizon_months is None or len({f.metric for f in forecasts}) > 1):
            raise ValueError("forecast feeds require a shared target metric and horizon")
        if not forecasts and self.horizon_months is not None:
            raise ValueError("a forecast horizon requires a forecast feed")
        if (
            len(self.target_mappings) != len(forecasts)
            or {mapping.feed for mapping in self.target_mappings} != set(forecasts)
            or any(
                (mapping.geographic_unit, mapping.horizon_months)
                != (self.geographic_unit, self.horizon_months)
                for mapping in self.target_mappings
            )
        ):
            raise ValueError("each forecast feed requires one matching reviewed target mapping")
        activity = {feed for feed in self.feeds if feed.model is None}
        if (
            len(self.activity_mappings) != len(activity)
            or {mapping.feed for mapping in self.activity_mappings} != activity
        ):
            raise ValueError("each activity feed requires one versioned reviewed target mapping")
        targets = {feed.metric for feed in forecasts}
        targets.update(mapping.target for mapping in self.activity_mappings)
        if len(targets) != 1:
            raise ValueError("all forecast and activity mappings must share the same target")
        activity_mappings = sorted(self.activity_mappings, key=lambda item: _feed_key(item.feed))
        object.__setattr__(self, "activity_mappings", tuple(activity_mappings))
        object.__setattr__(self, "feeds", tuple(sorted(self.feeds, key=_feed_key)))
        mappings = sorted(self.target_mappings, key=lambda mapping: _feed_key(mapping.feed))
        object.__setattr__(self, "target_mappings", tuple(mappings))
        return self


class OperationalQuery(_Record):
    provider: str = Field(min_length=1)
    country: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    period_start: date
    period_end: date

    def receipt_id_for(self, collection_id: str) -> str:
        return _fingerprint(
            "operational-receipt-v1",
            collection_id,
            self.provider,
            self.country,
            self.event_type,
            self.period_start.isoformat(),
            self.period_end.isoformat(),
        )


class OperationalAttestation(_Record):
    """Archived audit of the exact filtered operational query."""

    query: OperationalQuery
    evidence_ref: str = Field(min_length=1)
    kind: Literal["operational_events"]
    pagination_exhausted: Literal[True]
    unrestricted: Literal[True]
    counts_reconciled: Literal[True]


class OperationalReceipt(OperationalQuery):
    receipt_id: str = Field(min_length=1)
    collection_id: str = Field(min_length=1)
    attestation: OperationalAttestation | None = None
    completed_at: datetime | None = None
    available_at: datetime
    status: Literal["verified_complete", "partial", "truncated", "stale", "ambiguous"]
    source_ids: tuple[str, ...]
    temporal_classification: Literal["recent_operational"]

    @model_validator(mode="after")
    def validate_receipt(self):
        utc_day(self.available_at)
        if self.receipt_id != self.receipt_id_for(self.collection_id):
            raise ValueError("receipt ID must bind the collection and exact query scope")
        if self.period_start > self.period_end or any(not item.strip() for item in self.source_ids):
            raise ValueError("invalid receipt window or source identifiers")
        if self.completed_at is not None:
            utc_day(self.completed_at)
            if self.completed_at > self.available_at:
                raise ValueError("receipt completion must precede availability")
        if self.status == "verified_complete" and (
            self.completed_at is None or utc_day(self.completed_at) <= self.period_end
        ):
            raise ValueError("complete coverage requires completed retrieval of a closed window")
        if self.status == "verified_complete" and (
            self.attestation is None
            or self.attestation.query.receipt_id_for(self.collection_id) != self.receipt_id
        ):
            raise ValueError("complete coverage requires an audit of the exact operational query")
        object.__setattr__(self, "source_ids", tuple(sorted(set(self.source_ids))))
        return self


class Observation(_Record):
    feed: Feed
    region: str
    geographic_unit: str
    period_start: date
    period_end: date
    available_on: date
    value: float | None = Field(ge=0)
    complete: bool
    source_ids: tuple[str, ...] = Field(min_length=1)
    receipt: OperationalReceipt | None = None
    target_mapping: TargetMapping | None = None
    probability_scale: Literal["0-1"] | None = None
    horizon_months: int | None = Field(default=None, ge=1)
    issue_date: date | None = None
    target_start: date | None = None
    target_end: date | None = None

    _reject_boolean = field_validator("value", mode="before")(reject_boolean_prediction)

    @model_validator(mode="after")
    def valid_measurement(self):
        if self.period_start > self.period_end:
            raise ValueError("observation period must be ordered")
        if any(not identifier.strip() for identifier in self.source_ids):
            raise ValueError("source identifiers must not be blank")
        if self.feed.model is not None:
            mapping = self.target_mapping
            if (
                self.receipt is not None
                or self.probability_scale != "0-1"
                or mapping is None
                or not self.feed.version
                or (mapping.feed, mapping.geographic_unit, mapping.horizon_months)
                != (self.feed, self.geographic_unit, self.horizon_months)
            ):
                raise ValueError(
                    "forecast observations require an explicit versioned target mapping"
                )
            if self.value is not None and self.value > 1:
                raise ValueError("forecast probabilities must be fractions")
            if (
                not self.issue_date
                or not self.target_start
                or not self.target_end
                or not self.period_start <= self.issue_date <= self.period_end
                or not self.issue_date <= self.target_start <= self.target_end
                or self.available_on < self.issue_date
            ):
                raise ValueError("forecast observations require comparable issue and target dates")
        elif (
            self.target_mapping is not None
            or self.probability_scale is not None
            or (self.complete and self.available_on <= self.period_end)
            or self.horizon_months is not None
            or self.issue_date is not None
            or self.target_start is not None
            or self.target_end is not None
            or (self.value is not None and not self.value.is_integer())
        ):
            raise ValueError("observed activity requires closed windows and integer counts")
        elif self.receipt is None:
            if self.complete:
                raise ValueError(
                    "complete activity observations require matching verified coverage"
                )
        else:
            coverage = self.receipt
            if (
                coverage.provider,
                coverage.event_type,
                coverage.country,
                coverage.period_start,
                coverage.period_end,
                utc_day(coverage.available_at),
                "country",
                coverage.receipt_id,
            ) != (
                self.feed.provider,
                self.feed.metric,
                self.region,
                self.period_start,
                self.period_end,
                self.available_on,
                self.geographic_unit,
                self.source_ids[0],
            ):
                raise ValueError(
                    "activity observation does not match the receipt scope or availability"
                )
            if self.complete and (
                coverage.status != "verified_complete"
                or self.value != len(coverage.source_ids)
                or self.source_ids[1:] != coverage.source_ids
            ):
                raise ValueError(
                    "complete activity observations require matching verified coverage"
                )
        return self

    @classmethod
    def from_forecast(
        cls,
        signal: NormalizedForecastSignal,
        *,
        mapping: TargetMapping,
        period_start: date,
        period_end: date,
    ) -> "Observation":
        """Accept an aligned external probability under a reviewed target mapping."""
        reject_boolean_prediction(signal.prediction)
        issued = utc_day(signal.issue_date)
        retrieved = utc_day(signal.retrieved_at)
        target = (utc_day(signal.target_start), utc_day(signal.target_end))
        if (
            signal.unit != "probability"
            or signal.scale != "0-1"
            or signal.alignment_status != "aligned"
            or signal.retrieved_at < signal.issue_date
            or (
                signal.provider,
                signal.model_name,
                signal.model_version,
                signal.target_variable,
                signal.geographic_unit,
                signal.horizon_months,
            )
            != (
                mapping.feed.provider,
                mapping.feed.model,
                mapping.feed.version,
                mapping.source_target,
                mapping.geographic_unit,
                mapping.horizon_months,
            )
            or target != mapping.window(issued)
        ):
            raise ValueError("forecast signal is unsupported or misaligned")
        return cls(
            feed=mapping.feed,
            region=signal.location,
            geographic_unit=signal.geographic_unit,
            period_start=period_start,
            period_end=period_end,
            available_on=retrieved,
            value=signal.prediction,
            complete=True,
            source_ids=(signal.source_record_id,),
            horizon_months=signal.horizon_months,
            issue_date=issued,
            target_start=target[0],
            target_end=target[1],
            target_mapping=mapping,
            probability_scale="0-1",
        )

    @classmethod
    def from_events(
        cls, events: Iterable[NormalizedOperationalEvent], *, receipt: OperationalReceipt
    ) -> "Observation":
        """Count distinct records whose identities match a verified operational receipt."""
        receipt = OperationalReceipt.model_validate(receipt)
        ids = set()
        for event in events:
            if (
                event.provider != receipt.provider
                or event.country != receipt.country
                or event.event_type != receipt.event_type
                or event.alignment_status != "aligned"
                or event.temporal_classification != "recent_operational"
                or not receipt.period_start <= utc_day(event.event_date) <= receipt.period_end
                or utc_day(event.retrieved_at) > utc_day(receipt.available_at)
                or event.event_date > event.retrieved_at
                or event.retrieved_at > (receipt.completed_at or receipt.available_at)
                or (
                    event.updated_at is not None
                    and (
                        event.updated_at.utcoffset() is None
                        or event.updated_at > event.retrieved_at
                    )
                )
                or not event.source_record_id.strip()
            ):
                raise ValueError("event source, geography, availability or period is incompatible")
            ids.add(event.source_record_id)
        complete = receipt.status == "verified_complete"
        if complete and ids != set(receipt.source_ids):
            raise ValueError("event identities do not match the coverage receipt")
        return cls(
            feed=Feed(provider=receipt.provider, metric=receipt.event_type),
            region=receipt.country,
            geographic_unit="country",
            period_start=receipt.period_start,
            period_end=receipt.period_end,
            available_on=utc_day(receipt.available_at),
            value=len(ids) if complete else None,
            complete=complete,
            source_ids=(receipt.receipt_id, *sorted(ids)),
            receipt=receipt,
        )


class Evidence(_Record):
    indicator: str
    level: Level
    baseline: tuple[Observation, ...]
    current: tuple[Observation, ...]
    explanation: str


SlotStatus = Literal["usable", "stale", "missing", "incomplete", "ambiguous", "incompatible"]


class SlotCoverage(_Record):
    period_end: date
    status: SlotStatus
    observations: tuple[Observation, ...]


class Coverage(_Record):
    feed: Feed
    expected: int
    usable: int
    latest_period_end: date | None
    age_days: int | None
    slots: tuple[SlotCoverage, ...]


class WarningRecord(_Record):
    method_version: Literal["early-warning-v1"] = "early-warning-v1"
    advisory_only: Literal[True] = True
    mode: Literal["live", "replay"]
    scope: Scope
    thresholds: Thresholds
    period_start: date
    period_end: date
    as_of: date
    revision_cutoff: date
    held_level: Level
    level: Level
    previous_level: Level
    candidate_level: Level
    event_id: str | None
    coverage: tuple[Coverage, ...]
    data_issues: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    retained_evidence: tuple[Evidence, ...]
    explanation: str


class State(_Record):
    stream_id: str
    mode: Literal["live", "replay"]
    period_end: date
    as_of: date
    revision_cutoff: date
    level: Literal[Level.NORMAL, Level.WATCH, Level.WARNING, Level.CRITICAL]
    recovery_count: int = Field(default=0, ge=0)
    recovery_candidate: Level | None = None
    evidence: tuple[Evidence, ...] = ()


def _fingerprint(*parts: str) -> str:
    return sha256(dumps(parts, ensure_ascii=False).encode()).hexdigest()


def stream_id(scope: Scope, thresholds: Thresholds) -> str:
    scope = Scope.model_validate(scope)
    return _fingerprint("early-warning-v1", scope.model_dump_json(), thresholds.model_dump_json())


def _inspect(
    scope: Scope,
    observations: tuple[Observation, ...],
    end: date,
    as_of: date,
    policy: Thresholds,
    revision_cutoff: date,
) -> tuple[tuple[Coverage, ...], set[str], dict[Feed, tuple[Observation, ...]]]:
    cadence = timedelta(days=policy.cadence_days)
    ends = tuple(end - i * cadence for i in reversed(range(policy.minimum_observations)))
    coverage = []
    issues = set()
    series = {}
    mappings = {mapping.feed: mapping for mapping in scope.target_mappings}
    for feed in scope.feeds:
        slots: dict[date, list[Observation]] = {}
        incompatible = set()
        name = f"{feed.provider}/{feed.model or feed.metric}"
        for row in observations:
            if row.feed != feed or row.period_end not in ends or row.available_on > revision_cutoff:
                continue
            row = Observation.model_validate(row)
            alternatives = slots.setdefault(row.period_end, [])
            if row not in alternatives:
                alternatives.append(row)
            label = f"{name} on {row.period_end}"
            problem = None
            if (row.region, row.geographic_unit) != (scope.region, scope.geographic_unit):
                problem = "Geographic mismatch"
            elif feed.model is not None and row.horizon_months != scope.horizon_months:
                problem = "Forecast horizon mismatch"
            elif row.period_start != row.period_end - cadence + timedelta(days=1):
                problem = "Incompatible observation period"
            elif feed.model is not None and (
                row.target_start,
                row.target_end,
            ) != mappings[feed].window(row.issue_date or row.period_end):
                problem = "Forecast has an incompatible window"
            elif feed.model is not None and row.target_mapping != mappings[feed]:
                problem = "Forecast target mapping mismatch"
            if problem:
                incompatible.add(row.period_end)
                issues.add(f"{problem} for {label}.")
        statuses = []
        usable = {}
        for slot in ends:
            entries = tuple(sorted(slots.get(slot, []), key=lambda row: row.model_dump_json()))
            status: SlotStatus = "usable"
            if slot in incompatible:
                status = "incompatible"
            elif len(entries) > 1:
                status = "ambiguous"
            elif not entries:
                status = "missing"
            elif not entries[0].complete or entries[0].value is None:
                status = "incomplete"
            else:
                usable[slot] = entries[0]
            if status != "usable":
                issues.add(f"{status.capitalize()} observation for {name} on {slot}.")
            statuses.append(SlotCoverage(period_end=slot, status=status, observations=entries))
        latest = max(usable, default=None)
        age = (as_of - latest).days if latest else None
        stale = age is not None and age > policy.maximum_age_days
        if stale:
            issues.add(f"Stale observations for {name}.")
            statuses = [
                item.model_copy(update={"status": "stale"}) if item.status == "usable" else item
                for item in statuses
            ]
        coverage.append(
            Coverage(
                feed=feed,
                expected=len(ends),
                usable=len(usable),
                latest_period_end=latest,
                age_days=age,
                slots=tuple(statuses),
            )
        )
        if not stale and len(usable) == len(ends):
            rows = tuple(usable[slot] for slot in ends)
            target_end = rows[-1].target_end
            if target_end is not None and target_end < as_of:
                issues.add(f"Expired forecast target for {name}.")
                continue
            identifiers = [
                identifier
                for row in rows
                for identifier in set(
                    row.source_ids if row.receipt is None else row.receipt.source_ids
                )
            ]
            if len(set(identifiers)) != len(identifiers):
                kind = "forecast" if feed.model is not None else "operational event"
                issues.add(f"Repeated {kind} identity across slots for {name}.")
                continue
            series[feed] = rows

    model_coverage = [item for item in coverage if item.feed.model is not None]
    if len(model_coverage) > 1:
        for slots_at_period in zip(*(item.slots for item in model_coverage), strict=True):
            aligned = {
                (slot.observations[0].target_start, slot.observations[0].target_end)
                for slot in slots_at_period
                if slot.status in {"usable", "stale"}
            }
            if len(aligned) > 1:
                issues.add(
                    f"Forecast model target periods are incompatible on "
                    f"{slots_at_period[0].period_end}."
                )
    return tuple(coverage), issues, series


def _value(row: Observation) -> float:
    assert row.value is not None
    return row.value


def _indicators(
    series: dict[Feed, tuple[Observation, ...]],
    policy: Thresholds,
) -> list[Evidence]:
    evidence = []
    for feed, rows in series.items():
        values = [_value(row) for row in rows]
        if feed.model is None:
            old, new = values[-2:]
            if new - old >= policy.activity_increase and new >= old * policy.activity_ratio:
                evidence.append(
                    Evidence(
                        indicator="activity_jump",
                        level=Level.WARNING,
                        baseline=rows[-2:-1],
                        current=rows[-1:],
                        explanation="Reported activity crossed both jump thresholds.",
                    )
                )
            if new - values[0] >= policy.activity_increase and all(
                b - a >= policy.activity_trend_step for a, b in pairwise(values)
            ):
                evidence.append(
                    Evidence(
                        indicator="sustained_activity_increase",
                        level=Level.WARNING,
                        baseline=rows[:-1],
                        current=rows[-1:],
                        explanation="Reported activity rose at each step and exceeded net change.",
                    )
                )
            continue
        if round(values[-1] - values[-2], 12) >= policy.probability_jump:
            evidence.append(
                Evidence(
                    indicator="forecast_jump",
                    level=Level.WARNING,
                    baseline=rows[-2:-1],
                    current=rows[-1:],
                    explanation="Forecast probability rose by the jump threshold.",
                )
            )
        if round(values[-1] - values[0], 12) >= policy.trend_total and all(
            round(b - a, 12) >= policy.trend_step for a, b in pairwise(values)
        ):
            evidence.append(
                Evidence(
                    indicator="sustained_deterioration",
                    level=Level.WARNING,
                    baseline=rows[:-1],
                    current=rows[-1:],
                    explanation="Forecast rose at each step and exceeded net change.",
                )
            )
        if max(values[:-1]) <= policy.low_baseline and values[-1] >= policy.emerging_current:
            evidence.append(
                Evidence(
                    indicator="emerging_risk",
                    level=Level.WATCH,
                    baseline=rows[:-1],
                    current=rows[-1:],
                    explanation="Forecast crossed the threshold from a low baseline.",
                )
            )
    return evidence


def _model_comparison(
    series: dict[Feed, tuple[Observation, ...]],
    policy: Thresholds,
) -> list[Evidence]:
    models = [rows for feed, rows in series.items() if feed.model is not None]
    if len(models) < 2:
        return []
    evidence = []
    forecasts = [rows[-1] for rows in models]
    low = min(forecasts, key=_value)
    high = max(forecasts, key=_value)
    if round(_value(high) - _value(low), 12) >= policy.disagreement:
        evidence.append(
            Evidence(
                indicator="model_disagreement",
                level=Level.WATCH,
                baseline=(low,),
                current=(high,),
                explanation="Comparable models differ by the configured probability spread.",
            )
        )
    movements = [(rows[-2], rows[-1]) for feed, rows in series.items() if feed.model is not None]
    rising = max(movements, key=lambda pair: _value(pair[1]) - _value(pair[0]))
    falling = min(movements, key=lambda pair: _value(pair[1]) - _value(pair[0]))
    if (
        round(_value(rising[1]) - _value(rising[0]), 12) >= policy.probability_jump
        and round(_value(falling[0]) - _value(falling[1]), 12) >= policy.probability_jump
    ):
        evidence.append(
            Evidence(
                indicator="opposing_model_movements",
                level=Level.WATCH,
                baseline=(rising[0], falling[0]),
                current=(rising[1], falling[1]),
                explanation="Comparable models moved in opposite directions by the jump threshold.",
            )
        )
    return evidence


_DEFAULT_THRESHOLDS = Thresholds()


def evaluate(
    scope: Scope,
    observations: Iterable[Observation],
    *,
    period_end: date,
    as_of: date,
    thresholds: Thresholds = _DEFAULT_THRESHOLDS,
    previous: State | None = None,
    revision_cutoff: date | None = None,
    mode: Literal["live", "replay"] = "live",
) -> tuple[WarningRecord, State]:
    """Evaluate one closed period, returning a JSON-ready record and resumable state."""
    if as_of < period_end:
        raise ValueError("evaluation cannot precede the close of the observation period")
    cutoff = revision_cutoff if revision_cutoff is not None else as_of
    if cutoff > as_of:
        raise ValueError("revision cutoff cannot follow as_of")
    scope = Scope.model_validate(scope)
    stream = stream_id(scope, thresholds)
    if previous and (
        previous.stream_id != stream
        or previous.mode != mode
        or previous.period_end > period_end
        or previous.as_of > as_of
        or previous.revision_cutoff > cutoff
    ):
        raise ValueError("previous state must match scope and policy and cannot be from the future")
    coverage, issues, series = _inspect(
        scope, tuple(observations), period_end, as_of, thresholds, cutoff
    )
    comparison = _model_comparison(series, thresholds) if not issues else []
    evidence = _indicators(series, thresholds) + comparison if not issues else []

    prior = previous.level if previous else Level.NORMAL
    recovery = 0
    event_id = None
    prior_evidence = previous.evidence if previous else ()
    retained: tuple[Evidence, ...] = ()
    if issues:
        candidate = level = Level.INSUFFICIENT_DATA
        explanation = "Required observations are missing, stale, ambiguous or incompatible."
        retained = prior_evidence
        state = State(
            stream_id=stream,
            mode=mode,
            period_end=period_end,
            as_of=as_of,
            revision_cutoff=cutoff,
            level=prior,
            evidence=retained,
        )
    else:
        candidate = max(
            (item.level for item in evidence), key=_SEVERITY.index, default=Level.NORMAL
        )
        indicators = {item.indicator for item in evidence}
        corroborated = "activity_jump" in indicators and bool(
            indicators & {"forecast_jump", "sustained_deterioration"}
        )
        if corroborated and not comparison:
            candidate = Level.CRITICAL
        level = candidate
        explanation = {
            Level.NORMAL: "No escalation threshold was crossed.",
            Level.WATCH: "An emerging risk or model disagreement crossed a threshold.",
            Level.WARNING: "A significant change or sustained deterioration crossed a threshold.",
            Level.CRITICAL: "Observed activity and forecast increases both crossed thresholds.",
        }[candidate]
        if _SEVERITY.index(candidate) < _SEVERITY.index(prior):
            same_candidate = previous is not None and previous.recovery_candidate == candidate
            if previous and previous.period_end == period_end:
                recovery = previous.recovery_count if same_candidate else 1
            elif (
                previous
                and same_candidate
                and (period_end - previous.period_end).days == thresholds.cadence_days
            ):
                recovery = previous.recovery_count + 1
            else:
                recovery = 1
            if recovery < thresholds.recovery_observations:
                level = prior
                retained = prior_evidence
                explanation = "Previous advisory level held pending consecutive recovery periods."
            else:
                recovery = 0
                explanation = "Consecutive lower readings met the recovery requirement."
        if mode == "live" and _SEVERITY.index(level) > _SEVERITY.index(prior):
            event_id = _fingerprint(stream, period_end.isoformat(), level.value)
        assert level != Level.INSUFFICIENT_DATA
        state = State(
            stream_id=stream,
            mode=mode,
            period_end=period_end,
            as_of=as_of,
            revision_cutoff=cutoff,
            level=level,
            recovery_count=recovery,
            recovery_candidate=candidate if recovery else None,
            evidence=retained or tuple(evidence),
        )

    return WarningRecord(
        mode=mode,
        scope=scope,
        thresholds=thresholds,
        period_start=period_end
        - timedelta(days=thresholds.cadence_days * thresholds.minimum_observations - 1),
        period_end=period_end,
        as_of=as_of,
        revision_cutoff=cutoff,
        held_level=state.level,
        level=level,
        previous_level=prior,
        candidate_level=candidate,
        event_id=event_id,
        coverage=coverage,
        data_issues=tuple(sorted(issues)),
        evidence=tuple(evidence),
        retained_evidence=retained,
        explanation=explanation,
    ), state
