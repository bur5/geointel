"""Offline what-if analysis with explicit, illustrative score changes."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

RULE_VERSION = "daily-additive-v1"
MAX_SCORE = 10_000
LIMITATIONS = (
    "Illustrative score changes are supplied by the caller and have no validated causal meaning.",
    "The baseline is held constant. The model has no inferred interactions or feedback.",
    "Sensitivity varies one input at a time. It is not a confidence interval.",
    "Scores are not probabilities. Branches have no assigned likelihood.",
)

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Region = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]*:[A-Za-z0-9_-]+$")]
Score = Annotated[int, Field(ge=0, le=MAX_SCORE)]
Delta = Annotated[int, Field(ge=-MAX_SCORE, le=MAX_SCORE)]
Day = Annotated[int, Field(ge=1, le=3660)]


class _Input(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", revalidate_instances="always"
    )


class Indicator(_Input):
    name: Label
    score: Score


class Baseline(_Input):
    region: Region
    start: date
    indicators: Annotated[tuple[Indicator, ...], Field(min_length=1)]
    provenance: Annotated[tuple[Label, ...], Field(min_length=1)]
    uncertainty: Label

    @model_validator(mode="after")
    def unique_indicators(self) -> "Baseline":
        names = {indicator.name for indicator in self.indicators}
        if len(names) != len(self.indicators):
            raise ValueError("baseline indicator names must be unique")
        return self


class Change(_Input):
    indicator: Label
    delta: Delta


class Event(_Input):
    id: Label
    region: Region
    day: Day
    assumption: Label
    changes: Annotated[tuple[Change, ...], Field(min_length=1)]
    provenance: Annotated[tuple[Label, ...], Field(min_length=1)]
    uncertainty: Label

    @model_validator(mode="after")
    def unique_changes(self) -> "Event":
        if len({change.indicator for change in self.changes}) != len(self.changes):
            raise ValueError("an event may change each indicator only once")
        return self


class Branch(_Input):
    name: Label
    assumption: Label
    events: tuple[Event, ...] = ()


class Scenario(_Input):
    baseline: Baseline
    horizon_days: Day
    branches: Annotated[tuple[Branch, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def check_alignment(self) -> "Scenario":
        if self.horizon_days > (date.max - self.baseline.start).days:
            raise ValueError("horizon extends beyond the supported calendar")
        if len({branch.name for branch in self.branches}) != len(self.branches):
            raise ValueError("branch names must be unique")
        indicators = {indicator.name for indicator in self.baseline.indicators}
        for branch in self.branches:
            if len({event.id for event in branch.events}) != len(branch.events):
                raise ValueError(f"event IDs must be unique within branch {branch.name!r}")
            for event in branch.events:
                if event.region != self.baseline.region:
                    raise ValueError(f"event {event.id!r} region differs from baseline region")
                if event.day > self.horizon_days:
                    raise ValueError(f"event {event.id!r} falls outside the simulation horizon")
                for change in event.changes:
                    if change.indicator not in indicators:
                        raise ValueError(f"missing baseline indicator {change.indicator!r}")
        return self


class SensitivityInput(_Input):
    branch: Label
    event_id: Label
    indicator: Label
    replacement_delta: Delta


@dataclass(frozen=True)
class IndicatorResult:
    name: str
    score: int
    delta_from_baseline: int
    clipped: bool


@dataclass(frozen=True)
class Step:
    date: date
    event_ids: tuple[str, ...]
    indicators: tuple[IndicatorResult, ...]


@dataclass(frozen=True)
class BranchResult:
    branch: Branch
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class SensitivityResult:
    input: SensitivityInput
    original_delta: int
    endpoint_score: int
    endpoint_delta_from_unvaried: int


@dataclass(frozen=True)
class Comparison:
    baseline: Baseline
    horizon_days: int
    branches: tuple[BranchResult, ...]
    sensitivity: tuple[SensitivityResult, ...]
    rule_version: str = RULE_VERSION
    limitations: tuple[str, ...] = LIMITATIONS


def _run(
    scenario: Scenario, branch: Branch, variation: SensitivityInput | None = None
) -> BranchResult:
    baseline = {indicator.name: indicator.score for indicator in scenario.baseline.indicators}
    names = sorted(baseline)
    scores = baseline.copy()
    schedule: dict[int, list[Event]] = {}
    for event in branch.events:
        schedule.setdefault(event.day, []).append(event)

    steps = []
    for day in range(scenario.horizon_days + 1):
        events = schedule.get(day, [])
        totals: dict[str, int] = {}
        for event in events:
            for change in event.changes:
                delta = change.delta
                if variation and (event.id, change.indicator) == (
                    variation.event_id,
                    variation.indicator,
                ):
                    delta = variation.replacement_delta
                totals[change.indicator] = totals.get(change.indicator, 0) + delta

        readings = []
        for name in names:
            raw = scores[name] + totals.get(name, 0)
            score = min(MAX_SCORE, max(0, raw))
            scores[name] = score
            readings.append(IndicatorResult(name, score, score - baseline[name], raw != score))
        steps.append(
            Step(
                scenario.baseline.start + timedelta(days=day),
                tuple(sorted(event.id for event in events)),
                tuple(readings),
            )
        )
    return BranchResult(branch, tuple(steps))


def simulate(scenario: Scenario, *, sensitivity: tuple[SensitivityInput, ...] = ()) -> Comparison:
    """Compare caller-ordered branches and optionally vary one event delta per rerun."""
    scenario = Scenario.model_validate(scenario)
    branches = tuple(_run(scenario, branch) for branch in scenario.branches)
    by_name = {result.branch.name: result for result in branches}
    variations = []
    for requested in sensitivity:
        variation = SensitivityInput.model_validate(requested)
        result = by_name.get(variation.branch)
        if result is None:
            raise ValueError(f"unknown sensitivity branch {variation.branch!r}")
        original = next(
            (
                change.delta
                for event in result.branch.events
                if event.id == variation.event_id
                for change in event.changes
                if change.indicator == variation.indicator
            ),
            None,
        )
        if original is None:
            raise ValueError("sensitivity target must name an existing event indicator")
        varied = _run(scenario, result.branch, variation)
        original_score = next(
            item.score for item in result.steps[-1].indicators if item.name == variation.indicator
        )
        varied_score = next(
            item.score for item in varied.steps[-1].indicators if item.name == variation.indicator
        )
        variations.append(
            SensitivityResult(variation, original, varied_score, varied_score - original_score)
        )
    return Comparison(scenario.baseline, scenario.horizon_days, branches, tuple(variations))
