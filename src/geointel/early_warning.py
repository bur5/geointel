"""Deterministic, advisory evaluation of comparable geopolitical risk observations."""

from collections.abc import Iterable
from datetime import date, timedelta
from enum import StrEnum
from hashlib import sha256
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from geointel.domain.schemas import NormalizedForecastSignal, NormalizedOperationalEvent


class Level(StrEnum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


_SEVERITY = (Level.NORMAL, Level.WATCH, Level.WARNING, Level.CRITICAL)


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class Feed(_Record):
    provider: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    model: str | None = Field(default=None, min_length=1)
    version: str | None = None


class Scope(_Record):
    region: str = Field(min_length=1)
    geographic_unit: str = Field(min_length=1)
    horizon_months: int | None = Field(default=None, ge=1)
    feeds: tuple[Feed, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def comparable_feeds(self):
        forecasts = [feed for feed in self.feeds if feed.model is not None]
        if len(set(self.feeds)) != len(self.feeds):
            raise ValueError("feeds must be unique")
        if forecasts and (self.horizon_months is None or len({f.metric for f in forecasts}) > 1):
            raise ValueError("forecast feeds require a shared target metric and horizon")
        if not forecasts and self.horizon_months is not None:
            raise ValueError("a forecast horizon requires a forecast feed")
        return self


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
    horizon_months: int | None = Field(default=None, ge=1)
    issue_date: date | None = None
    target_start: date | None = None
    target_end: date | None = None

    @model_validator(mode="after")
    def valid_measurement(self):
        if self.period_start > self.period_end:
            raise ValueError("observation period must be ordered")
        if any(not identifier.strip() for identifier in self.source_ids):
            raise ValueError("source identifiers must not be blank")
        if self.feed.model is not None:
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
            self.available_on < self.period_end
            or self.horizon_months is not None
            or self.issue_date is not None
            or self.target_start is not None
            or self.target_end is not None
            or (self.value is not None and not self.value.is_integer())
        ):
            raise ValueError("observed activity requires closed windows and integer counts")
        return self

    @classmethod
    def from_forecast(
        cls, signal: NormalizedForecastSignal, *, period_start: date, period_end: date
    ) -> "Observation":
        """Accept provider-declared fractional probability signals with verified semantics."""
        if (
            signal.unit != "probability"
            or signal.scale not in (None, "0-1")
            or signal.alignment_status != "aligned"
            or not period_start <= signal.issue_date.date() <= period_end
            or signal.target_start.date() < signal.issue_date.date()
        ):
            raise ValueError("forecast signal is unsupported or misaligned")
        return cls(
            feed=Feed(
                provider=signal.provider,
                metric=signal.target_variable,
                model=signal.model_name,
                version=signal.model_version,
            ),
            region=signal.location,
            geographic_unit=signal.geographic_unit,
            period_start=period_start,
            period_end=period_end,
            available_on=max(signal.issue_date.date(), signal.retrieved_at.date()),
            value=signal.prediction,
            complete=True,
            source_ids=(signal.source_record_id,),
            horizon_months=signal.horizon_months,
            issue_date=signal.issue_date.date(),
            target_start=signal.target_start.date(),
            target_end=signal.target_end.date(),
        )

    @classmethod
    def from_events(
        cls,
        events: Iterable[NormalizedOperationalEvent],
        *,
        provider: str,
        country: str,
        event_type: str,
        period_start: date,
        period_end: date,
        available_on: date,
        coverage_id: str,
        complete: bool,
    ) -> "Observation":
        """Count distinct aligned country records from one documented collection window."""
        ids = set()
        for event in events:
            if (
                event.provider != provider
                or event.country != country
                or event.alignment_status != "aligned"
                or event.temporal_classification != "recent_operational"
                or not period_start <= event.event_date.date() <= period_end
                or event.retrieved_at.date() > available_on
            ):
                raise ValueError("event source, geography, availability or period is incompatible")
            if event.event_type == event_type:
                ids.add(event.source_record_id)
        if not coverage_id.strip():
            raise ValueError("a coverage record is required")
        return cls(
            feed=Feed(provider=provider, metric=event_type),
            region=country,
            geographic_unit="country",
            period_start=period_start,
            period_end=period_end,
            available_on=available_on,
            value=len(ids) if complete else None,
            complete=complete,
            source_ids=(coverage_id, *sorted(ids)),
        )


class Evidence(_Record):
    indicator: str
    level: Level
    baseline: tuple[Observation, ...]
    current: tuple[Observation, ...]
    explanation: str


class Coverage(_Record):
    feed: Feed
    expected: int
    usable: int
    latest_period_end: date | None
    age_days: int | None


class WarningRecord(_Record):
    method_version: Literal["early-warning-v1"] = "early-warning-v1"
    advisory_only: Literal[True] = True
    scope: Scope
    thresholds: Thresholds
    period_start: date
    period_end: date
    as_of: date
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
    period_end: date
    as_of: date
    level: Literal[Level.NORMAL, Level.WATCH, Level.WARNING, Level.CRITICAL]
    recovery_count: int = Field(default=0, ge=0)
    evidence: tuple[Evidence, ...] = ()


def _fingerprint(*parts: str) -> str:
    return sha256("\n".join(parts).encode()).hexdigest()


def _forecast_window(row: Observation) -> tuple[int, int]:
    issue, start, end = row.issue_date, row.target_start, row.target_end
    return (
        (start.year - issue.year) * 12 + start.month - issue.month,
        (end.year - start.year) * 12 + end.month - start.month,
    )


def _inspect(
    scope: Scope,
    observations: tuple[Observation, ...],
    end: date,
    as_of: date,
    policy: Thresholds,
) -> tuple[tuple[Coverage, ...], set[str], dict[Feed, tuple[Observation, ...]]]:
    cadence = timedelta(days=policy.cadence_days)
    ends = tuple(end - i * cadence for i in reversed(range(policy.minimum_observations)))
    coverage = []
    issues = set()
    series = {}
    for feed in scope.feeds:
        slots = {}
        for row in observations:
            if row.feed != feed or row.period_end not in ends or row.available_on > as_of:
                continue
            label = f"{feed.provider}/{feed.model or feed.metric} on {row.period_end}"
            if (row.region, row.geographic_unit) != (scope.region, scope.geographic_unit):
                issues.add(f"Geographic mismatch for {label}.")
                continue
            if feed.model is not None and row.horizon_months != scope.horizon_months:
                issues.add(f"Forecast horizon mismatch for {label}.")
                continue
            if row.period_start != row.period_end - cadence + timedelta(days=1):
                issues.add(f"Incompatible observation period for {label}.")
                continue
            entries = slots.setdefault(row.period_end, [])
            if row not in entries:
                entries.append(row)
        usable = {}
        for slot in ends:
            entries = slots.get(slot, [])
            if len(entries) == 1 and entries[0].complete and entries[0].value is not None:
                usable[slot] = entries[0]
            else:
                reason = "Ambiguous" if len(entries) > 1 else "Missing or incomplete"
                name = f"{feed.provider}/{feed.model or feed.metric}"
                issues.add(f"{reason} observation for {name} on {slot}.")
        latest = max(usable, default=None)
        age = (as_of - latest).days if latest else None
        stale = age is not None and age > policy.maximum_age_days
        if stale:
            issues.add(f"Stale observations for {feed.provider}/{feed.model or feed.metric}.")
        coverage.append(
            Coverage(
                feed=feed,
                expected=len(ends),
                usable=len(usable),
                latest_period_end=latest,
                age_days=age,
            )
        )
        if not stale and len(usable) == len(ends):
            rows = tuple(usable[slot] for slot in ends)
            if feed.model is not None and rows[-1].target_end < as_of:
                issues.add(f"Expired forecast target for {feed.provider}/{feed.model}.")
            elif feed.model is not None and (
                len({row.source_ids for row in rows}) != len(rows)
                or len({_forecast_window(row) for row in rows}) != 1
            ):
                issues.add(
                    f"Repeated forecast or incompatible window for {feed.provider}/{feed.model}."
                )
            else:
                series[feed] = rows
    return tuple(coverage), issues, series


def _indicators(
    series: dict[Feed, tuple[Observation, ...]],
    policy: Thresholds,
) -> list[Evidence]:
    evidence = []
    for feed, rows in series.items():
        values = [row.value for row in rows]
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
    issues: set[str],
) -> Evidence | None:
    forecasts = [rows[-1] for feed, rows in series.items() if feed.model is not None]
    if len(forecasts) < 2:
        return None
    if len({(row.target_start, row.target_end) for row in forecasts}) != 1:
        issues.add("Forecast model target periods are incompatible.")
        return None
    low = min(forecasts, key=lambda row: row.value)
    high = max(forecasts, key=lambda row: row.value)
    if round(high.value - low.value, 12) >= policy.disagreement:
        return Evidence(
            indicator="model_disagreement",
            level=Level.WATCH,
            baseline=(low,),
            current=(high,),
            explanation="Comparable models differ by the configured probability spread.",
        )
    movements = [(rows[-2], rows[-1]) for feed, rows in series.items() if feed.model is not None]
    rising = max(movements, key=lambda pair: pair[1].value - pair[0].value)
    falling = min(movements, key=lambda pair: pair[1].value - pair[0].value)
    if (
        round(rising[1].value - rising[0].value, 12) >= policy.probability_jump
        and round(falling[0].value - falling[1].value, 12) >= policy.probability_jump
    ):
        return Evidence(
            indicator="opposing_model_movements",
            level=Level.WATCH,
            baseline=(rising[0], falling[0]),
            current=(rising[1], falling[1]),
            explanation="Comparable models moved in opposite directions by the jump threshold.",
        )
    return None


_DEFAULT_THRESHOLDS = Thresholds()


def evaluate(
    scope: Scope,
    observations: Iterable[Observation],
    *,
    period_end: date,
    as_of: date,
    thresholds: Thresholds = _DEFAULT_THRESHOLDS,
    previous: State | None = None,
) -> tuple[WarningRecord, State]:
    """Evaluate one closed period, returning a JSON-ready record and resumable state."""
    if as_of < period_end:
        raise ValueError("evaluation cannot precede the close of the observation period")
    stream = _fingerprint("early-warning-v1", scope.model_dump_json(), thresholds.model_dump_json())
    if previous and (
        previous.stream_id != stream or previous.period_end > period_end or previous.as_of > as_of
    ):
        raise ValueError("previous state must match scope and policy and cannot be from the future")
    coverage, issues, series = _inspect(scope, tuple(observations), period_end, as_of, thresholds)
    comparison = _model_comparison(series, thresholds, issues)
    evidence = _indicators(series, thresholds)
    if comparison:
        evidence.append(comparison)

    prior = previous.level if previous else Level.NORMAL
    recovery = 0
    event_id = None
    prior_evidence = previous.evidence if previous else ()
    retained = ()
    if issues:
        candidate = level = Level.INSUFFICIENT_DATA
        explanation = "Required observations are missing, stale, ambiguous or incompatible."
        retained = prior_evidence
        state = State(
            stream_id=stream, period_end=period_end, as_of=as_of, level=prior, evidence=retained
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
            if previous and previous.period_end == period_end:
                recovery = previous.recovery_count
            elif previous and (period_end - previous.period_end).days == thresholds.cadence_days:
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
        if _SEVERITY.index(level) > _SEVERITY.index(prior):
            event_id = _fingerprint(stream, period_end.isoformat(), level.value)
        state = State(
            stream_id=stream,
            period_end=period_end,
            as_of=as_of,
            level=level,
            recovery_count=recovery,
            evidence=retained or tuple(evidence),
        )

    return WarningRecord(
        scope=scope,
        thresholds=thresholds,
        period_start=period_end
        - timedelta(days=thresholds.cadence_days * thresholds.minimum_observations - 1),
        period_end=period_end,
        as_of=as_of,
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
