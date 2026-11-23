"""Deterministic advisory classifications over normalized GEOINTEL observations."""

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from enum import IntEnum, StrEnum
from hashlib import sha256
from json import dumps, loads
from math import isfinite


class Level(IntEnum):
    INSUFFICIENT_DATA = -1
    NORMAL = 0
    WATCH = 1
    WARNING = 2
    CRITICAL = 3


class Kind(StrEnum):
    PROBABILITY = "probability"
    EVENTS = "events"


@dataclass(frozen=True)
class Region:
    unit: str
    identifier: str


@dataclass(frozen=True, order=True)
class Stream:
    kind: Kind
    source: str
    series: str


@dataclass(frozen=True)
class Scope:
    region: Region
    target: str
    horizon_months: int | None
    streams: tuple[Stream, ...]
    cadence_days: int = 7

    def __post_init__(self):
        if not self.streams or len(set(self.streams)) != len(self.streams):
            raise ValueError("Declare unique expected streams")
        if self.cadence_days < 1:
            raise ValueError("Cadence must be positive")
        models = [s.series for s in self.streams if s.kind == Kind.PROBABILITY]
        if len(models) != len(set(models)):
            raise ValueError("Declare only one stream per predictive model")
        if models and (self.horizon_months is None or self.horizon_months < 1):
            raise ValueError("Forecast streams require a positive horizon")


@dataclass(frozen=True)
class Observation:
    region: Region
    target: str
    stream: Stream
    period_end: date
    available_on: date
    value: float | None
    record_id: str
    horizon_months: int | None = None
    target_window: tuple[date, date] | None = None


@dataclass(frozen=True)
class Thresholds:
    """Provisional engineering defaults, pending empirical evaluation."""

    min_observations: int = 4
    max_age_days: int = 7
    recovery_observations: int = 2
    probability_jump: float = 0.15
    probability_trend: float = 0.12
    trend_step: float = 0.02
    low_risk: float = 0.05
    emerging_risk: float = 0.12
    model_spread: float = 0.25
    event_increase: int = 5
    event_ratio: float = 2.0

    def __post_init__(self):
        if self.min_observations < 3 or self.recovery_observations < 2:
            raise ValueError("Require at least three observations and two recovery observations")
        if self.max_age_days < 0 or self.event_increase < 1:
            raise ValueError("Invalid freshness or count threshold")
        if not isfinite(self.event_ratio) or self.event_ratio <= 1:
            raise ValueError("Event ratio must exceed one")
        if not 0 <= self.low_risk < self.emerging_risk <= 1:
            raise ValueError("Emerging risk must exceed the low-risk ceiling")
        if not all(
            0 < threshold <= 1
            for threshold in (
                self.probability_jump,
                self.probability_trend,
                self.trend_step,
                self.model_spread,
            )
        ):
            raise ValueError("Probability change thresholds must be in (0, 1]")


@dataclass(frozen=True)
class State:
    """Carry forward per scope and policy, applying evaluations in chronological order."""

    scope: Scope
    thresholds: Thresholds
    level: Level
    period_end: date
    recovery_count: int = 0
    recovery_level: Level | None = None
    supporting_evidence: str = "[]"


def _reference(row: Observation) -> dict:
    return {
        "period_end": row.period_end.isoformat(),
        "available_on": row.available_on.isoformat(),
        "source": row.stream.source,
        "series": row.stream.series,
        "record_id": row.record_id,
        "value": row.value,
        "horizon_months": row.horizon_months,
        "target_window": [day.isoformat() for day in row.target_window]
        if row.target_window
        else None,
    }


def _valid_value(row: Observation) -> bool:
    value = row.value
    if value is None or not isfinite(value) or value < 0:
        return False
    return value <= 1 if row.stream.kind == Kind.PROBABILITY else value % 1 == 0


def _evidence(
    code: str, explanation: str, baseline: float, current: float, rows: list[Observation]
) -> dict:
    return {
        "code": code,
        "explanation": explanation,
        "baseline": baseline,
        "current": current,
        "observations": [_reference(row) for row in rows],
    }


def _indicators(series: dict[Stream, list[Observation]], policy: Thresholds) -> list[dict]:
    indicators = []
    probability_windows = {}
    for stream, rows in series.items():
        first, previous, latest = rows[0], rows[-2], rows[-1]
        start, prior, current = first.value, previous.value, latest.value
        if stream.kind == Kind.EVENTS:
            if current - prior >= policy.event_increase and current >= prior * policy.event_ratio:
                indicators.append(
                    _evidence(
                        "activity_surge",
                        "Event count passed both surge thresholds.",
                        prior,
                        current,
                        rows[-2:],
                    )
                )
            continue
        if latest.target_window is not None:
            probability_windows.setdefault(latest.target_window, []).append(latest)
        if round(current - prior, 12) >= policy.probability_jump:
            indicators.append(
                _evidence(
                    "forecast_jump",
                    "Forecast probability rose sharply in one update.",
                    prior,
                    current,
                    rows[-2:],
                )
            )
        if round(current - start, 12) >= policy.probability_trend and all(
            round(b.value - a.value, 12) >= policy.trend_step
            for a, b in zip(rows, rows[1:], strict=False)
        ):
            indicators.append(
                _evidence(
                    "sustained_deterioration",
                    "Every update rose and the total rise qualified.",
                    start,
                    current,
                    rows,
                )
            )
        if (
            max(row.value for row in rows[:-1]) <= policy.low_risk
            and current >= policy.emerging_risk
        ):
            indicators.append(
                _evidence(
                    "emerging_risk",
                    "Forecast crossed the emerging-risk threshold from a low baseline.",
                    max(row.value for row in rows[:-1]),
                    current,
                    rows,
                )
            )
    for probability_rows in probability_windows.values():
        if len(probability_rows) < 2:
            continue
        low = min(probability_rows, key=lambda row: row.value)
        high = max(probability_rows, key=lambda row: row.value)
        if round(high.value - low.value, 12) >= policy.model_spread:
            indicators.append(
                _evidence(
                    "model_disagreement",
                    "Comparable model forecasts differ by the configured spread.",
                    low.value,
                    high.value,
                    [low, high],
                )
            )
    return indicators


def _classify(indicators: list[dict]) -> Level:
    codes = {item["code"] for item in indicators}
    forecast = bool(codes & {"forecast_jump", "sustained_deterioration"})
    activity = "activity_surge" in codes
    if forecast and activity and "model_disagreement" not in codes:
        return Level.CRITICAL
    if forecast or activity:
        return Level.WARNING
    return Level.WATCH if codes else Level.NORMAL


def _transition(
    previous: State | None,
    candidate: Level,
    end: date,
    scope: Scope,
    policy: Thresholds,
    indicators: list[dict],
) -> State:
    if candidate == Level.INSUFFICIENT_DATA:
        held = previous.level if previous else Level.INSUFFICIENT_DATA
        support = previous.supporting_evidence if previous else "[]"
        return State(scope, policy, held, end, supporting_evidence=support)
    if previous is None or candidate >= previous.level:
        return State(scope, policy, candidate, end, supporting_evidence=dumps(indicators))
    if end == previous.period_end:
        return previous
    consecutive = end - previous.period_end == timedelta(days=scope.cadence_days)
    count = (
        previous.recovery_count + 1 if consecutive and previous.recovery_level == candidate else 1
    )
    if count >= policy.recovery_observations:
        return State(scope, policy, candidate, end, supporting_evidence=dumps(indicators))
    return State(scope, policy, previous.level, end, count, candidate, previous.supporting_evidence)


def evaluate(
    scope: Scope,
    observations: list[Observation],
    *,
    period_end: date,
    as_of: date,
    thresholds: Thresholds = Thresholds(),
    previous: State | None = None,
) -> tuple[dict, State]:
    """Return a JSON-ready snapshot and the state to carry into the next evaluation."""
    if as_of < period_end:
        raise ValueError("Evaluation date precedes the observation period")
    if previous and (
        previous.scope != scope
        or previous.thresholds != thresholds
        or period_end < previous.period_end
    ):
        raise ValueError("Previous state belongs to another scope, policy, or later period")

    dates = [
        period_end - timedelta(days=scope.cadence_days * offset)
        for offset in reversed(range(thresholds.min_observations))
    ]
    slots = {(stream, day): set() for stream in sorted(scope.streams) for day in dates}
    issues = set()
    for row in observations:
        key = (row.stream, row.period_end)
        if key not in slots or row.available_on > as_of:
            continue
        if row.region != scope.region:
            issues.add("geographic_mismatch")
            continue
        expected_horizon = scope.horizon_months if row.stream.kind == Kind.PROBABILITY else None
        if row.horizon_months != expected_horizon:
            issues.add("horizon_mismatch")
            continue
        if row.target != scope.target:
            issues.add("target_mismatch")
            continue
        if row.target_window is not None and row.target_window[0] > row.target_window[1]:
            issues.add("invalid_target_window")
            continue
        if not row.record_id or not _valid_value(row):
            issues.add("missing_or_invalid_value")
            continue
        if row.available_on < row.period_end:
            issues.add("invalid_availability_date")
            continue
        slots[key].add(row)

    series = {stream: [] for stream in sorted(scope.streams)}
    coverage = []
    for (stream, day), rows in slots.items():
        if len(rows) == 1:
            series[stream].append(next(iter(rows)))
        elif rows:
            issues.add("ambiguous_observation")
        else:
            issues.add("missing_observation")
        coverage.append(
            {
                "stream": asdict(stream),
                "period_end": day.isoformat(),
                "usable": len(rows) == 1,
            }
        )

    age = (as_of - period_end).days
    if age > thresholds.max_age_days:
        issues.add("stale_observation")
    model_streams = [stream for stream in series if stream.kind == Kind.PROBABILITY]
    if len(model_streams) > 1:
        windows_by_date = {day: set() for day in dates}
        for stream in model_streams:
            for row in series[stream]:
                windows_by_date[row.period_end].add(row.target_window)
        if any(None in windows for windows in windows_by_date.values()):
            issues.add("missing_target_window")
        if any(len(windows - {None}) > 1 for windows in windows_by_date.values()):
            issues.add("target_window_mismatch")
    indicators = [] if issues else _indicators(series, thresholds)
    candidate = Level.INSUFFICIENT_DATA if issues else _classify(indicators)
    state = _transition(previous, candidate, period_end, scope, thresholds, indicators)
    level = candidate if issues else state.level

    event_id = None
    if level >= Level.WATCH and (previous is None or level != previous.level):
        identity = {**asdict(scope), "streams": [asdict(s) for s in sorted(scope.streams)]}
        event_key = dumps(
            [1, identity, asdict(thresholds), period_end.isoformat(), level.name],
            sort_keys=True,
        )
        event_id = sha256(event_key.encode()).hexdigest()

    if issues:
        explanation = "Classification unavailable because input coverage or comparability failed."
    elif level > candidate:
        explanation = "The advisory level is held pending consecutive recovery observations."
    elif level == Level.CRITICAL:
        explanation = (
            "A qualifying forecast increase coincided with an activity surge "
            "without a qualifying model spread in the supplied inputs."
        )
    elif level == Level.WARNING:
        explanation = "A forecast increase or activity surge met the WARNING threshold."
        if any(item["code"] == "model_disagreement" for item in indicators):
            explanation += " Model disagreement caps the candidate level at WARNING."
    elif level == Level.WATCH:
        explanation = "Emerging risk or model disagreement met the WATCH threshold."
    else:
        explanation = "The complete observation window had no qualifying escalation."

    return {
        "schema_version": 1,
        "advisory_only": True,
        "region": asdict(scope.region),
        "target": scope.target,
        "forecast_horizon_months": scope.horizon_months,
        "period_start": (dates[0] - timedelta(days=scope.cadence_days - 1)).isoformat(),
        "period_end": period_end.isoformat(),
        "as_of": as_of.isoformat(),
        "level": level.name,
        "candidate_level": candidate.name,
        "event_id": event_id,
        "explanation": explanation,
        "indicators": indicators,
        "held_level_indicators": loads(state.supporting_evidence)
        if level > candidate and not issues
        else [],
        "freshness": {
            "period_end_age_days": age,
            "max_age_days": thresholds.max_age_days,
            "latest_usable_period_end": [
                {
                    "stream": asdict(stream),
                    "period_end": rows[-1].period_end.isoformat() if rows else None,
                }
                for stream, rows in series.items()
            ],
        },
        "completeness": {
            "expected": len(slots),
            "usable": sum(len(rows) for rows in series.values()),
            "issues": sorted(issues),
            "slots": coverage,
        },
        "provenance": [_reference(row) for rows in series.values() for row in rows],
        "thresholds": asdict(thresholds),
    }, state
