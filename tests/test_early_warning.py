from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from json import dumps
from uuid import UUID

import pytest

from geointel.domain.models import AnalysisRun, Event, Forecast, ForecastSignal, Location
from geointel.early_warning import Kind, Observation, Region, Scope, Stream, Thresholds, evaluate
from geointel.early_warning_inputs import (
    event_count_observation,
    forecast_observation,
    signal_observation,
)

REGION = Region("country", "Synthetic")
FORECAST = Stream(Kind.PROBABILITY, "synthetic", "model-a")
OTHER_MODEL = Stream(Kind.PROBABILITY, "synthetic", "model-b")
EVENTS = Stream(Kind.EVENTS, "synthetic", "events")
START = date(2026, 1, 7)
WEEK = timedelta(days=7)
DEFAULT_POLICY = Thresholds()


def observations(values, stream=FORECAST):
    result = []
    for index, value in enumerate(values):
        day = START + WEEK * index
        probability = stream.kind == Kind.PROBABILITY
        result.append(
            Observation(
                REGION,
                "internal_armed_conflict",
                stream,
                day,
                day,
                value,
                f"{stream.series}-{index}",
                3 if probability else None,
                (day + timedelta(days=1), day + timedelta(days=90)) if probability else None,
            )
        )
    return result


def run(rows, index=3, *, streams=(FORECAST,), as_of=None, previous=None, policy=DEFAULT_POLICY):
    end = START + WEEK * index
    return evaluate(
        Scope(REGION, "internal_armed_conflict", 3, streams),
        rows,
        period_end=end,
        as_of=as_of or end,
        previous=previous,
        thresholds=policy,
    )


@pytest.mark.parametrize(
    ("values", "level", "indicators"),
    [
        ([0.20, 0.21, 0.20, 0.35], "WARNING", {"forecast_jump"}),
        ([0.10, 0.14, 0.18, 0.22], "WARNING", {"sustained_deterioration"}),
        ([0.20, 0.21, 0.20, 0.21], "NORMAL", set()),
        ([0.03, 0.04, 0.04, 0.12], "WATCH", {"emerging_risk"}),
    ],
)
def test_forecast_rules(values, level, indicators):
    record, _ = run(observations(values))
    assert record["level"] == level
    assert {i["code"] for i in record["indicators"]} == indicators
    assert record["completeness"]["usable"] == 4
    assert record["freshness"]["period_end_age_days"] == 0
    assert [r["value"] for r in record["provenance"]] == values
    assert record["advisory_only"]
    dumps(record, allow_nan=False)


def test_activity_and_forecast_corroboration():
    event_rows = observations([2, 2, 3, 8], EVENTS)
    record, _ = run(event_rows, streams=(EVENTS,))
    assert record["level"] == "WARNING"
    assert record["indicators"][0]["baseline"] == 3
    assert record["indicators"][0]["current"] == 8
    record, _ = run(event_rows + observations([0.20, 0.21, 0.20, 0.36]), streams=(FORECAST, EVENTS))
    assert record["level"] == "CRITICAL"


@pytest.mark.parametrize("corroboration", [False, True])
def test_conflicting_models_limit_severity(corroboration):
    rows = observations([0.60, 0.60, 0.60, 0.77] if corroboration else [0.60] * 4)
    rows += observations([0.40, 0.35, 0.30, 0.25], OTHER_MODEL)
    streams = (FORECAST, OTHER_MODEL)
    if corroboration:
        rows += observations([1, 1, 1, 6], EVENTS)
        streams += (EVENTS,)
    record, _ = run(rows, streams=streams)
    assert record["level"] == ("WARNING" if corroboration else "WATCH")
    spread = next(i for i in record["indicators"] if i["code"] == "model_disagreement")
    assert (spread["baseline"], spread["current"]) == (0.25, 0.77 if corroboration else 0.60)


@pytest.mark.parametrize(
    ("changes", "issue"),
    [
        ({"region": Region("grid", "Synthetic")}, "geographic_mismatch"),
        ({"region": Region("country", "Elsewhere")}, "geographic_mismatch"),
        ({"horizon_months": 6}, "horizon_mismatch"),
        ({"value": None}, "missing_or_invalid_value"),
        ({"value": float("nan")}, "missing_or_invalid_value"),
        ({"available_on": START + 4 * WEEK}, "missing_observation"),
    ],
)
def test_incompatible_or_missing_obs(changes, issue):
    rows = observations([0.2] * 4)
    rows[-1] = replace(rows[-1], **changes)
    record, _ = run(rows)
    assert record["level"] == "INSUFFICIENT_DATA"
    assert issue in record["completeness"]["issues"]
    assert record["completeness"]["usable"] == 3


def test_target_window_mismatch():
    main = observations([0.2] * 4)
    other = observations([0.7] * 4, OTHER_MODEL)
    other[-1] = replace(other[-1], target_window=(START + 4 * WEEK, START + 20 * WEEK))
    record, _ = run(main + other, streams=(FORECAST, OTHER_MODEL))
    assert record["level"] == "INSUFFICIENT_DATA"
    assert record["completeness"]["issues"] == ["target_window_mismatch"]


def test_stale_and_missing_streams():
    rows = observations([0.02] * 4)
    record, _ = run(rows, as_of=START + 4 * WEEK + timedelta(days=1))
    assert record["level"] == "INSUFFICIENT_DATA"
    assert record["completeness"]["issues"] == ["stale_observation"]
    record, _ = run(rows, streams=(FORECAST, EVENTS))
    assert record["level"] == "INSUFFICIENT_DATA"
    assert record["completeness"]["usable"] == 4
    assert record["completeness"]["expected"] == 8
    record, _ = run(rows, policy=Thresholds(min_observations=5))
    assert record["level"] == "INSUFFICIENT_DATA"


def test_duplicate_and_ambiguous_observations_and_events():
    rows = observations([0.21, 0.21, 0.21, 0.40, 0.58])
    record, state = run(rows)
    assert record["event_id"]
    assert run(list(reversed(rows + [rows[2]])))[0] == record
    assert run(rows, previous=state)[0]["event_id"] is None
    repeated, _ = run(rows, 4, previous=state)
    assert repeated["level"] == "WARNING"
    assert repeated["event_id"] is None
    conflict = replace(rows[3], value=0.85, record_id="contradictory")
    ambiguous, _ = run(rows + [conflict])
    assert ambiguous["level"] == "INSUFFICIENT_DATA"
    assert ambiguous["completeness"]["issues"] == ["ambiguous_observation"]


def test_recovery_requires_distinct_consecutive_complete_windows():
    rows = observations([0.21, 0.21, 0.21, 0.40, 0.40, 0.40, 0.40, 0.40])
    _, state = run(rows)
    held, state = run(rows, 4, previous=state)
    assert (held["level"], held["candidate_level"]) == ("WARNING", "NORMAL")
    assert held["held_level_indicators"][0]["code"] == "forecast_jump"
    replayed, state = run(rows, 4, previous=state)
    assert replayed == held
    missing, state = run(rows[:5], 5, previous=state)
    assert missing["level"] == "INSUFFICIENT_DATA"
    held, state = run(rows, 6, previous=state)
    assert held["level"] == "WARNING"
    recovered, _ = run(rows, 7, previous=state)
    assert recovered["level"] == "NORMAL"


def test_existing_record_adapters():
    now = datetime(2026, 1, 7, tzinfo=UTC)
    location = Location(name="Kingdom of Spain")
    run = AnalysisRun(status="completed", location=location, completed_at=now)
    forecast = Forecast(
        id=UUID(int=1),
        analysis_run=run,
        conflict_type="internal_armed_conflict",
        horizon_months=3,
        probability_low=0.1,
        probability_high=0.3,
        created_at=now,
    )
    item = forecast_observation(forecast, model="demo")
    assert item.region == Region("country", "Spain")
    assert item.value == 0.2
    forecast.probability_low = None
    assert forecast_observation(forecast, model="demo").value is None

    signal = ForecastSignal(
        provider="synthetic",
        geographic_unit="country",
        source_location="Spain",
        source_record_id="signal-1",
        target_variable=item.target,
        horizon_months=3,
        issue_date=now,
        retrieved_at=now,
        created_at=now,
        target_start=now + WEEK,
        target_end=now + 13 * WEEK,
        alignment_status="aligned",
        prediction=0.25,
        unit="probability",
        scale="0-1",
    )
    assert signal_observation(signal, model="demo").value == 0.25
    signal.scale = "count"
    with pytest.raises(ValueError, match="probability"):
        signal_observation(signal, model="demo")

    event = Event(
        provenance={"provider": "ACLED", "alignment_status": "aligned", "country": "Spain"},
        event_type="Battles",
        source_record_id="event-1",
        occurred_at=now,
        created_at=now,
    )
    kwargs = dict(
        region=item.region,
        target=item.target,
        series="battles",
        event_types=frozenset({"Battles"}),
        period_end=now.date(),
        available_on=now.date(),
        cadence_days=7,
        coverage_record_id="synthetic-coverage",
    )
    assert event_count_observation([event, event], **kwargs).value == 1
    assert event_count_observation([], **kwargs).value == 0
    with pytest.raises(ValueError, match="verified country coverage"):
        event_count_observation([], **{**kwargs, "coverage_record_id": ""})
