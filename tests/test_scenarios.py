import json
import os
import subprocess
import sys
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from geointel.scenarios import (
    Baseline,
    Branch,
    Change,
    Event,
    Indicator,
    Scenario,
    SensitivityInput,
    simulate,
)


@pytest.fixture
def baseline():
    return Baseline(
        region="synthetic:example",
        start=date(2024, 2, 28),
        indicators=(Indicator(name="tension", score=5000),),
        provenance=("synthetic fixture",),
        uncertainty="Illustrative values.",
    )


def event(delta, *, id="incident", day=1, region="synthetic:example", indicator="tension"):
    return Event(
        id=id,
        region=region,
        day=day,
        assumption="Synthetic event changes the indicator.",
        changes=(Change(indicator=indicator, delta=delta),),
        provenance=("synthetic fixture",),
        uncertainty="Magnitude varies with the assumption.",
    )


def scenario(baseline, *events, horizon=3):
    return Scenario(
        baseline=baseline,
        horizon_days=horizon,
        branches=(Branch(name="branch", assumption="Synthetic branch", events=events),),
    )


def test_replay_branching_and_sensitivity(baseline):
    start = event(1000)
    definition = Scenario(
        baseline=baseline,
        horizon_days=3,
        branches=(
            Branch(
                name="negotiation",
                assumption="Negotiations make progress",
                events=(start, event(-2000, id="talks", day=2)),
            ),
            Branch(name="stalemate", assumption="No further change", events=(start,)),
        ),
    )
    variation = SensitivityInput(
        branch="negotiation", event_id="talks", indicator="tension", replacement_delta=-500
    )
    result = simulate(definition, sensitivity=(variation,))
    round_trip = Scenario.model_validate_json(definition.model_dump_json())
    assert result == simulate(round_trip, sensitivity=(variation,))
    peace, stalemate = result.branches
    assert peace.steps[:2] == stalemate.steps[:2]
    assert peace.steps[1].date == date(2024, 2, 29)
    assert peace.steps[2].event_ids == ("talks",)
    assert peace.steps[-1].indicators[0].delta_from_baseline == -1000
    assert stalemate.steps[-1].indicators[0].delta_from_baseline == 1000
    assert peace.branch == definition.branches[0]
    assert result.baseline == baseline
    assert result.sensitivity[0].original_delta == -2000
    assert result.sensitivity[0].endpoint_score == 5500
    assert result.sensitivity[0].endpoint_delta_from_unvaried == 1500


@pytest.mark.parametrize("horizon", [1, 3, 3660])
def test_daily_horizons_and_constant_control(baseline, horizon):
    (branch,) = simulate(scenario(baseline, horizon=horizon)).branches
    assert len(branch.steps) == horizon + 1
    assert branch.steps[-1].date == baseline.start + timedelta(days=horizon)
    assert all(step.indicators == branch.steps[0].indicators for step in branch.steps)


@pytest.mark.parametrize("horizon", [0, 3661, 1.5, True])
def test_invalid_horizon(baseline, horizon):
    with pytest.raises(ValidationError):
        scenario(baseline, horizon=horizon)


def test_calendar_overflow(baseline):
    with pytest.raises(ValidationError, match="supported calendar"):
        scenario(baseline.model_copy(update={"start": date.max}))


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"region": "synthetic:other"}, "region differs"),
        ({"day": 4}, "outside the simulation horizon"),
        ({"indicator": "missing"}, "missing baseline indicator"),
    ],
)
def test_unaligned_events(baseline, kwargs, error):
    with pytest.raises(ValidationError, match=error):
        scenario(baseline, event(100, **kwargs))


def test_required_inputs_and_invalid_assumptions(baseline):
    with pytest.raises(ValidationError):
        Scenario.model_validate({"horizon_days": 3, "branches": ()})
    with pytest.raises(ValidationError):
        Baseline.model_validate({**baseline.model_dump(), "indicators": ()})
    with pytest.raises(ValidationError):
        Branch(name="branch", assumption=" ")
    with pytest.raises(ValidationError, match="assumption"):
        Event.model_validate({**event(1).model_dump(), "assumption": ""})
    with pytest.raises(ValidationError, match="event IDs must be unique"):
        scenario(baseline, event(100), event(100))
    for invalid in (True, 0.5, float("inf"), float("nan"), 10001, -10001):
        with pytest.raises(ValidationError):
            Change(indicator="tension", delta=invalid)
    for invalid in (-1, 10001, True, "100"):
        with pytest.raises(ValidationError):
            Indicator(name="tension", score=invalid)


@pytest.mark.parametrize("field", ["branch", "event_id", "indicator"])
def test_invalid_sensitivity_target(baseline, field):
    target = {
        "branch": "branch",
        "event_id": "incident",
        "indicator": "tension",
        "replacement_delta": 0,
        field: "missing",
    }
    with pytest.raises(ValueError, match="sensitivity"):
        simulate(scenario(baseline, event(1)), sensitivity=(SensitivityInput(**target),))


def test_extremes_and_same_day_aggregation(baseline):
    events = (
        event(10000, id="increase"),
        event(-6000, id="offset"),
        event(10000, id="upper", day=2),
        event(-10000, id="lower", day=3),
        event(-10000, id="below", day=4),
    )
    (branch,) = simulate(scenario(baseline, *events, horizon=4)).branches
    (reversed_branch,) = simulate(scenario(baseline, *reversed(events), horizon=4)).branches
    assert branch.steps == reversed_branch.steps
    assert [step.indicators[0].score for step in branch.steps] == [5000, 9000, 10000, 0, 0]
    assert [step.indicators[0].clipped for step in branch.steps] == [
        False,
        False,
        True,
        False,
        True,
    ]


def test_changes_only_affect_named_indicators(baseline):
    baseline = Baseline.model_validate(
        {
            **baseline.model_dump(),
            "indicators": (*baseline.indicators, Indicator(name="trade", score=9000)),
        }
    )
    (branch,) = simulate(scenario(baseline, event(-300))).branches
    assert [
        (item.name, item.score, item.delta_from_baseline) for item in branch.steps[-1].indicators
    ] == [
        ("tension", 4700, -300),
        ("trade", 9000, 0),
    ]


def test_numerical_stability(baseline):
    horizon = 3660
    events = tuple(
        event(1 if day % 2 else -1, id=str(day), day=day) for day in range(1, horizon + 1)
    )
    (branch,) = simulate(scenario(baseline, *events, horizon=horizon)).branches
    assert all(step.indicators[0].score == 5000 + day % 2 for day, step in enumerate(branch.steps))


def test_reproducibility_in_fresh_processes(baseline):
    definition = scenario(baseline, event(13), event(-7, id="offset"), horizon=2)
    script = """
import json
import sys
from dataclasses import asdict
from geointel.scenarios import Scenario, simulate

result = simulate(Scenario.model_validate_json(sys.stdin.read()))
print(json.dumps([asdict(step) for step in result.branches[0].steps],
                 default=lambda value: value.isoformat(), sort_keys=True))
"""
    expected = [
        {
            "date": day,
            "event_ids": ids,
            "indicators": [
                {"name": "tension", "score": score, "delta_from_baseline": delta, "clipped": False}
            ],
        }
        for day, ids, score, delta in (
            ("2024-02-28", [], 5000, 0),
            ("2024-02-29", ["incident", "offset"], 5006, 6),
            ("2024-03-01", [], 5006, 6),
        )
    ]
    for seed, timezone in (("1", "UTC"), ("2", "America/Tijuana")):
        run = subprocess.run(
            [sys.executable, "-c", script],
            input=definition.model_dump_json(),
            env={**os.environ, "PYTHONHASHSEED": seed, "TZ": timezone},
            text=True,
            capture_output=True,
            check=True,
        )
        assert json.loads(run.stdout) == expected
