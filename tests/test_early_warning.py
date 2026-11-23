from datetime import UTC, date, datetime, timedelta

import pytest

from geointel.domain.schemas import NormalizedForecastSignal, NormalizedOperationalEvent
from geointel.early_warning import Feed, Level, Observation, Scope, State, Thresholds, evaluate

END = date(2026, 2, 21)
WEEK = timedelta(days=7)
MODEL_A = Feed(provider="synthetic", model="a", version="1", metric="internal_conflict")
MODEL_B = Feed(provider="synthetic", model="b", version="1", metric=MODEL_A.metric)
EVENTS = Feed(provider="synthetic", metric="Battles")


def scope(*feeds):
    return Scope(
        region="Exampleland",
        geographic_unit="country",
        feeds=feeds,
        horizon_months=1 if any(feed.model for feed in feeds) else None,
    )


def sample(feed, end, value):
    forecast = feed.model is not None
    return Observation(
        feed=feed,
        region="Exampleland",
        geographic_unit="country",
        period_start=end - timedelta(days=6),
        period_end=end,
        available_on=end,
        value=value,
        complete=value is not None,
        source_ids=(f"synthetic-{feed.model or feed.metric}-{end}",),
        horizon_months=1 if forecast else None,
        issue_date=end if forecast else None,
        target_start=date(2026, 3, 1) if forecast else None,
        target_end=date(2026, 3, 31) if forecast else None,
    )


def samples(feed, values, end=END):
    return [
        sample(feed, end - WEEK * offset, value)
        for offset, value in zip(reversed(range(len(values))), values, strict=True)
    ]


def assess(rows, *, feeds=(MODEL_A,), end=END, as_of=None, **options):
    return evaluate(scope(*feeds), rows, period_end=end, as_of=as_of or end, **options)


def indicators(record):
    return {reason.indicator for reason in record.evidence}


def test_sudden_escalation_with_two_signal_types():
    rows = samples(MODEL_A, [0.08, 0.09, 0.31]) + samples(EVENTS, [2, 3, 11])
    record, state = assess(rows, feeds=(MODEL_A, EVENTS))
    assert record.level == state.level == Level.CRITICAL
    assert indicators(record) == {"forecast_jump", "activity_jump", "emerging_risk"}
    assert record.event_id
    assert record.advisory_only
    result = record.model_dump(mode="json")
    assert result["scope"]["region"] == "Exampleland"
    assert result["period_start"] == "2026-02-01"
    forecast = result["evidence"][0]
    assert forecast["current"][0]["horizon_months"] == 1
    assert forecast["baseline"][0]["value"] == 0.09
    assert forecast["current"][0]["value"] == 0.31
    assert forecast["current"][0]["source_ids"] == ["synthetic-a-2026-02-21"]
    assert result["coverage"][0]["usable"] == result["coverage"][0]["expected"] == 3
    assert result["coverage"][0]["age_days"] == 0


@pytest.mark.parametrize(
    ("feed", "values", "expected"),
    [
        (MODEL_A, [0.14, 0.20, 0.25], "sustained_deterioration"),
        (EVENTS, [2, 5, 8], "sustained_activity_increase"),
        (EVENTS, [0, 0, 6], "activity_jump"),
    ],
)
def test_individual_changes(feed, values, expected):
    record, _ = assess(samples(feed, values), feeds=(feed,))
    assert record.level == Level.WARNING
    assert indicators(record) == {expected}


def test_emerging_risk_from_low_baseline():
    record, _ = assess(samples(MODEL_A, [0.10, 0.10, 0.20]))
    assert record.level == Level.WATCH
    assert indicators(record) == {"emerging_risk"}


def test_stable_conditions_and_configurable_thresholds():
    stable, _ = assess(samples(MODEL_A, [0.40, 0.39, 0.41]))
    conservative, _ = assess(
        samples(MODEL_A, [0.40, 0.40, 0.56]), thresholds=Thresholds(probability_jump=0.20)
    )
    for record in (stable, conservative):
        assert record.level == Level.NORMAL
        assert record.evidence == ()
        assert record.event_id is None


@pytest.mark.parametrize(
    ("second_model", "expected"),
    [
        ([0.10, 0.10, 0.10], "model_disagreement"),
        ([0.70, 0.60, 0.42], "opposing_model_movements"),
    ],
)
def test_conflicting_models_prevent_critical(second_model, expected):
    rows = (
        samples(MODEL_A, [0.20, 0.20, 0.40])
        + samples(MODEL_B, second_model)
        + samples(EVENTS, [1, 2, 10])
    )
    record, _ = assess(rows, feeds=(MODEL_A, MODEL_B, EVENTS))
    assert record.level == Level.WARNING
    assert expected in indicators(record)


def test_disagreement_alone_is_watch():
    rows = samples(MODEL_A, [0.40] * 3) + samples(MODEL_B, [0.10] * 3)
    record, _ = assess(rows, feeds=(MODEL_A, MODEL_B))
    assert record.level == Level.WATCH
    assert indicators(record) == {"model_disagreement"}


def test_missing_stale_and_not_yet_available_observations():
    rows = samples(MODEL_A, [0.20, 0.20, 0.21])
    missing, _ = assess(rows[1:])
    stale, _ = assess(rows, as_of=END + 2 * WEEK)
    late, _ = assess([*rows[:-1], rows[-1].model_copy(update={"available_on": END + WEEK})])
    incomplete, _ = assess([*rows[:-1], sample(MODEL_A, END, None)])
    for record in (missing, stale, late, incomplete):
        assert record.level == Level.INSUFFICIENT_DATA
        assert record.event_id is None
    assert stale.coverage[0].age_days == 14
    assert "Stale" in stale.data_issues[0]
    assert missing.coverage[0].usable == late.coverage[0].usable == 2


def test_expired_target_is_unusable_even_with_fresh_issue_window():
    rows = samples(MODEL_A, [0.20, 0.20, 0.40])
    rows = [
        row.model_copy(update={"target_start": date(2026, 2, 22), "target_end": date(2026, 2, 23)})
        for row in rows
    ]
    record, _ = assess(rows, as_of=END + timedelta(days=3))
    assert record.level == Level.INSUFFICIENT_DATA
    assert record.evidence == ()
    assert any("Expired forecast" in issue for issue in record.data_issues)


def test_duplicate_inputs_and_warning_events():
    rows = samples(MODEL_A, [0.20, 0.20, 0.46])
    first, state = assess(rows)
    replay, _ = assess(list(reversed(rows)) + rows)
    state = State.model_validate_json(state.model_dump_json())
    duplicate, _ = assess(rows, previous=state)
    subsequent, _ = assess(
        [*rows, sample(MODEL_A, END + WEEK, 0.63)],
        end=END + WEEK,
        previous=state,
    )
    assert first == replay
    assert first.event_id and first.event_id == replay.event_id
    assert duplicate.level == subsequent.level == Level.WARNING
    assert duplicate.event_id is subsequent.event_id is None
    ambiguous, _ = assess([*rows, sample(MODEL_A, END, 0.20)])
    assert ambiguous.level == Level.INSUFFICIENT_DATA
    assert any("Ambiguous" in issue for issue in ambiguous.data_issues)


@pytest.mark.parametrize(
    ("update", "problem"),
    [
        ({"region": "Elsewhere"}, "Geographic mismatch"),
        ({"geographic_unit": "grid"}, "Geographic mismatch"),
        ({"horizon_months": 3}, "Forecast horizon mismatch"),
        ({"target_end": date(2026, 4, 30)}, "incompatible window"),
    ],
)
def test_incompatible_observations(update, problem):
    rows = samples(MODEL_A, [0.20, 0.20, 0.45])
    record, _ = assess([*rows[:-1], rows[-1].model_copy(update=update)])
    assert record.level == Level.INSUFFICIENT_DATA
    assert any(problem in issue for issue in record.data_issues)


def test_models_must_have_identical_target_dates():
    second = [
        row.model_copy(update={"target_start": date(2026, 3, 2)})
        for row in samples(MODEL_B, [0.30] * 3)
    ]
    record, _ = assess(samples(MODEL_A, [0.10] * 3) + second, feeds=(MODEL_A, MODEL_B))
    assert record.level == Level.INSUFFICIENT_DATA
    assert any("model target periods" in issue for issue in record.data_issues)


def test_recovery_requires_distinct_consecutive_complete_periods():
    rows = samples(EVENTS, [1, 2, 10, 3, 3, 3, 3], end=END + 4 * WEEK)
    args = {"feeds": (EVENTS,)}
    elevated, state = assess(rows, **args)
    assert elevated.level == Level.WARNING
    day = END + WEEK
    first, state = assess(rows, end=day, previous=state, **args)
    retry, state = assess(rows, end=day, previous=state, **args)
    assert first.level == retry.level == Level.WARNING
    assert first.retained_evidence == elevated.evidence
    assert state.recovery_count == 1

    gap, state = assess(rows[:-3], end=END + 2 * WEEK, previous=state, **args)
    assert gap.level == Level.INSUFFICIENT_DATA
    assert state.level == Level.WARNING
    assert state.recovery_count == 0
    held, state = assess(rows, end=END + 3 * WEEK, previous=state, **args)
    recovered, state = assess(rows, end=END + 4 * WEEK, previous=state, **args)
    assert held.level == Level.WARNING
    assert recovered.level == state.level == Level.NORMAL
    assert recovered.event_id is None


def test_normalized_forecast_adapter_requires_explicit_probability_semantics():
    issued = datetime(2026, 2, 21, tzinfo=UTC)
    signal = NormalizedForecastSignal(
        provider=MODEL_A.provider,
        source_record_id="a1",
        model_name=MODEL_A.model,
        model_version=MODEL_A.version,
        geographic_unit="country",
        location="Exampleland",
        issue_date=issued,
        target_start=datetime(2026, 3, 1, tzinfo=UTC),
        target_end=datetime(2026, 3, 31, tzinfo=UTC),
        horizon_months=1,
        target_variable=MODEL_A.metric,
        prediction=0.20,
        unit="probability",
        scale="0-1",
        retrieved_at=issued,
    )
    args = {"period_start": END - timedelta(days=6), "period_end": END}
    row = Observation.from_forecast(signal, **args)
    assert row.feed == MODEL_A
    assert row.value == 0.20
    assert row.source_ids == ("a1",)
    for unit in (None, "forecast_event_count", "provider_native_units"):
        with pytest.raises(ValueError, match="unsupported or misaligned"):
            Observation.from_forecast(signal.model_copy(update={"unit": unit}), **args)


def test_normalized_events_require_coverage_and_count_distinct_aligned_records():
    reported = datetime(2026, 2, 21, tzinfo=UTC)
    event = NormalizedOperationalEvent(
        provider=EVENTS.provider,
        source_record_id="event-a",
        event_date=reported,
        event_type=EVENTS.metric,
        country="Exampleland",
        retrieved_at=reported,
    )
    args = {
        "provider": EVENTS.provider,
        "country": "Exampleland",
        "event_type": EVENTS.metric,
        "period_start": END - timedelta(days=6),
        "period_end": END,
        "available_on": END,
        "coverage_id": "collection-a",
    }
    complete = Observation.from_events([event, event], complete=True, **args)
    assert complete.feed == EVENTS
    assert complete.value == 1
    assert complete.source_ids == ("collection-a", "event-a")
    assert Observation.from_events([], complete=True, **args).value == 0
    assert Observation.from_events([], complete=False, **args).value is None
    with pytest.raises(ValueError, match="incompatible"):
        Observation.from_events(
            [event.model_copy(update={"country": "Elsewhere"})], complete=True, **args
        )
