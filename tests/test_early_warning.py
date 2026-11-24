import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.schema import CreateSchema, DropSchema

from geointel.domain.models import AnalysisRun, Event, Forecast, ForecastSignal
from geointel.domain.schemas import NormalizedForecastSignal, NormalizedOperationalEvent
from geointel.early_warning import (
    ActivityMapping,
    Feed,
    Level,
    Observation,
    OperationalAttestation,
    OperationalQuery,
    OperationalReceipt,
    Scope,
    State,
    TargetMapping,
    Thresholds,
    evaluate,
)
from geointel.early_warning_inputs import (
    event_count_observation,
    forecast_context,
    signal_observation,
)
from geointel.early_warning_store import checkpoints, history, metadata, persist_evaluation

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
        target_mappings=tuple(mapping(feed) for feed in feeds if feed.model),
        activity_mappings=tuple(
            ActivityMapping(feed=feed, target=MODEL_A.metric, version="1", review_ref="fixture")
            for feed in feeds
            if feed.model is None
        ),
        horizon_months=1 if any(feed.model for feed in feeds) else None,
    )


def mapping(feed):
    return TargetMapping(
        mapping_id=f"review-{feed.model}",
        feed=feed,
        source_target=feed.metric,
        geographic_unit="country",
        horizon_months=1,
        start_month_offset=1,
    )


def receipt(end, ids=(), status="verified_complete", *, country="Exampleland", feed=EVENTS):
    completed = datetime.combine(end + timedelta(days=1), time(), UTC)
    query = OperationalQuery(
        provider=feed.provider,
        country=country,
        event_type=feed.metric,
        period_start=end - timedelta(days=6),
        period_end=end,
    )
    collection_id = f"collection-{end}"
    return OperationalReceipt(
        **query.model_dump(),
        collection_id=collection_id,
        receipt_id=query.receipt_id_for(collection_id),
        attestation=OperationalAttestation(
            query=query,
            evidence_ref="test-audit",
            kind="operational_events",
            pagination_exhausted=True,
            unrestricted=True,
            counts_reconciled=True,
        )
        if status == "verified_complete"
        else None,
        source_ids=ids,
        status=status,
        temporal_classification="recent_operational",
        completed_at=completed,
        available_at=completed,
    )


def sample(feed, end, value):
    forecast = feed.model is not None
    ids = tuple(f"{end}-{i}" for i in range(value or 0)) if not forecast else ()
    coverage = receipt(end, ids, feed=feed) if not forecast else None
    target = mapping(feed).window(end) if forecast else (None, None)
    return Observation(
        feed=feed,
        region="Exampleland",
        geographic_unit="country",
        period_start=end - timedelta(days=6),
        period_end=end,
        available_on=end if forecast else end + timedelta(days=1),
        value=value,
        complete=value is not None,
        source_ids=(coverage.receipt_id, *coverage.source_ids)
        if coverage
        else (f"synthetic-{feed.model}-{end}",),
        receipt=coverage,
        target_mapping=mapping(feed) if forecast else None,
        probability_scale="0-1" if forecast else None,
        horizon_months=1 if forecast else None,
        issue_date=end if forecast else None,
        target_start=target[0],
        target_end=target[1],
    )


def samples(feed, values, end=END):
    return [
        sample(feed, end - WEEK * offset, value)
        for offset, value in zip(reversed(range(len(values))), values, strict=True)
    ]


def assess(rows, *, feeds=(MODEL_A,), end=END, as_of=None, **options):
    return evaluate(
        scope(*feeds),
        rows,
        period_end=end,
        as_of=as_of or (end + timedelta(days=1) if EVENTS in feeds else end),
        **options,
    )


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
    forecast = next(e for e in result["evidence"] if e["indicator"] == "forecast_jump")
    assert forecast["current"][0]["horizon_months"] == 1
    assert forecast["baseline"][0]["value"] == 0.09
    assert forecast["current"][0]["value"] == 0.31
    assert forecast["current"][0]["source_ids"] == ["synthetic-a-2026-02-21"]
    assert result["coverage"][0]["usable"] == result["coverage"][0]["expected"] == 3
    assert result["coverage"][0]["age_days"] == 1


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
    assert any("Stale" in issue for issue in stale.data_issues)
    assert missing.coverage[0].usable == late.coverage[0].usable == 2


def test_expired_target_is_unusable_even_with_fresh_issue_window():
    rows = samples(MODEL_A, [0.20, 0.20, 0.40])
    record, _ = assess(rows, as_of=date(2026, 4, 1), thresholds=Thresholds(maximum_age_days=50))
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
    if "geographic_unit" in update or "horizon_months" in update:
        update = {
            **update,
            "target_mapping": rows[-1].target_mapping.model_copy(update=update),
        }
    record, _ = assess([*rows[:-1], rows[-1].model_copy(update=update)])
    assert record.level == Level.INSUFFICIENT_DATA
    assert any(problem in issue for issue in record.data_issues)


def test_models_must_have_identical_target_dates():
    end = date(2026, 3, 15)
    second = samples(MODEL_B, [0.30] * 3, end=end)
    issue = date(2026, 2, 28)
    start, finish = mapping(MODEL_B).window(issue)
    second[0] = second[0].model_copy(
        update={"issue_date": issue, "target_start": start, "target_end": finish}
    )
    record, _ = assess(
        samples(MODEL_A, [0.10] * 3, end=end) + second,
        feeds=(MODEL_A, MODEL_B),
        end=end,
    )
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
    assert gap.held_level == state.level == Level.WARNING
    assert gap.retained_evidence == elevated.evidence
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
    args = {"period_start": END - timedelta(days=6), "period_end": END, "mapping": mapping(MODEL_A)}
    row = Observation.from_forecast(signal, **args)
    assert row.feed == MODEL_A
    assert row.value == 0.20
    assert row.source_ids == ("a1",)
    with pytest.raises(ValueError, match="Boolean"):
        NormalizedForecastSignal.model_validate({**signal.model_dump(), "prediction": True})
    with pytest.raises(ValueError, match="Boolean"):
        Observation.from_forecast(signal.model_copy(update={"prediction": True}), **args)
    for update in (
        {"unit": None},
        {"unit": "forecast_event_count"},
        {"unit": "provider_native_units"},
        {"scale": None},
        {"scale": "0-100"},
        {"target_variable": "different target"},
        {"model_version": "new"},
        {"target_end": datetime(2026, 3, 30, tzinfo=UTC)},
    ):
        with pytest.raises(ValueError, match="unsupported or misaligned"):
            Observation.from_forecast(signal.model_copy(update=update), **args)


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
    verified = receipt(END, ("event-a",))
    complete = Observation.from_events([event, event], receipt=verified)
    assert complete.feed == EVENTS
    assert complete.value == 1
    assert complete.source_ids == (verified.receipt_id, "event-a")
    assert Observation.from_events([], receipt=receipt(END)).value == 0
    with pytest.raises(ValueError, match="identities"):
        Observation.from_events([], receipt=verified)
    for status in ("partial", "truncated", "stale", "ambiguous"):
        incomplete = Observation.from_events([], receipt=receipt(END, status=status))
        assert incomplete.value is None
        record, _ = assess([*samples(EVENTS, [1, 2, 3])[:-1], incomplete], feeds=(EVENTS,))
        assert record.level == Level.INSUFFICIENT_DATA
        assert record.coverage[0].slots[-1].status == "incomplete"
    for update in ({"country": "Elsewhere"}, {"temporal_classification": "historical"}):
        with pytest.raises(ValueError, match="incompatible"):
            Observation.from_events([event.model_copy(update=update)], receipt=verified)


def test_recovery_requires_same_lower_candidate():
    rows = samples(MODEL_A, [0.05, 0.05, 0.21, 0.10, 0.08, 0.21, 0.22], end=END + 3 * WEEK)
    elevated, state = assess(rows, end=END - WEEK)
    assert elevated.level == Level.WARNING
    first, state = assess(rows, end=END, previous=state)
    assert first.candidate_level == Level.NORMAL
    second, state = assess(rows, end=END + WEEK, previous=state)
    assert second.candidate_level == Level.NORMAL
    assert state.level == Level.NORMAL

    # Starting one week later, the third window now has an emerging-risk candidate.
    _, state = assess(rows, end=END - WEEK)
    _, state = assess(rows, end=END + WEEK, previous=state)
    third, state = assess(rows, end=END + 2 * WEEK, previous=state)
    assert third.candidate_level == Level.WATCH
    assert state.level == Level.WARNING
    assert state.recovery_count == 1
    assert state.recovery_candidate == Level.WATCH


def test_reordered_feeds_and_cutoff():
    rows = samples(MODEL_A, [0.25, 0.25, 0.40]) + samples(MODEL_B, [0.20] * 3)
    first, _ = assess(rows, feeds=(MODEL_A, MODEL_B))
    second, _ = assess(reversed(rows), feeds=(MODEL_B, MODEL_A))
    assert first == second
    assert first.level == Level.WARNING and first.event_id
    replay, _ = assess(rows, feeds=(MODEL_A, MODEL_B), mode="replay")
    assert replay.level == first.level and replay.event_id is None
    assert replay.mode == "replay"
    late = [*rows[:-1], rows[-1].model_copy(update={"available_on": END + timedelta(days=1)})]
    record, _ = assess(
        late, feeds=(MODEL_A, MODEL_B), as_of=END + timedelta(days=1), revision_cutoff=END
    )
    assert record.level == Level.INSUFFICIENT_DATA
    assert record.coverage[-1].slots[-1].status == "missing"


def test_repeated_source_forecast_and_unexpected_version():
    rows = samples(MODEL_A, [0.25, 0.25, 0.40])
    repeated = rows[-1].model_copy(update={"source_ids": rows[0].source_ids})
    record, _ = assess([*rows[:-1], repeated])
    assert record.level == Level.INSUFFICIENT_DATA
    assert any("Repeated forecast" in message for message in record.data_issues)
    new_feed = MODEL_A.model_copy(update={"version": "2"})
    unexpected_version = sample(new_feed, END, 0.40)
    record, _ = assess([*rows[:-1], unexpected_version])
    assert record.coverage[0].slots[-1].status == "missing"


def test_forecast_context_preserves_unknowns_and_red_team_without_probability_substitution():
    stamp = datetime.combine(END, time(), UTC)
    run = AnalysisRun(
        id=uuid4(),
        status="completed",
        completed_at=stamp,
        red_team_output={"findings": ["Provider coverage changed."]},
    )
    assessment = Forecast(
        id=uuid4(),
        analysis_run=run,
        created_at=stamp,
        conflict_type="internal_conflict",
        question="Will qualifying conflict occur?",
        horizon_months=1,
        confidence="low",
        probability_low=0.1,
        probability_high=0.4,
        unknowns=["Coverage"],
    )
    contextual = forecast_context(assessment, as_of=END)
    assert (contextual["probability_low"], contextual["probability_high"]) == (0.1, 0.4)
    assert {"value", "prediction", "probability"}.isdisjoint(contextual)
    assert contextual["red_team"] == run.red_team_output
    contextual["unknowns"].append("New")
    contextual["red_team"]["findings"].clear()
    assert run.red_team_output == {"findings": ["Provider coverage changed."]}
    assert assessment.unknowns == ["Coverage"]
    assert (assessment.probability_low, assessment.probability_high) == (0.1, 0.4)
    with pytest.raises(ValueError, match="available"):
        forecast_context(assessment, as_of=END - timedelta(days=1))
    assessment.probability_low = assessment.probability_high = None
    contextual = forecast_context(assessment, as_of=END)
    assert contextual["probability_low"] is contextual["probability_high"] is None


def test_persisted_external_signal_uses_ingest_time_and_canonical_country():
    issued = datetime.combine(END, time(), UTC)
    stored = ForecastSignal(
        id=uuid4(),
        created_at=issued + timedelta(days=1),
        provider=MODEL_A.provider,
        source_record_id="external",
        model_name=MODEL_A.model,
        model_version=MODEL_A.version,
        geographic_unit="country",
        source_location="Kingdom of Spain",
        issue_date=issued,
        target_start=datetime(2026, 3, 1, tzinfo=UTC),
        target_end=datetime(2026, 3, 31, tzinfo=UTC),
        horizon_months=1,
        target_variable=MODEL_A.metric,
        prediction=0.20,
        unit="probability",
        scale="0-1",
        alignment_status="aligned",
        retrieved_at=issued,
    )
    row = signal_observation(
        stored, mapping=mapping(MODEL_A), period_start=END - timedelta(days=6), period_end=END
    )
    assert row.region == "Spain"
    assert row.available_on == END + timedelta(days=1)
    assert row.source_ids == ("external",)
    stored.provider = "VIEWS"
    stored.prediction = 1.0
    stored.provenance = {"raw_adapter_record": {"prediction": True}}
    with pytest.raises(ValueError, match="Boolean"):
        signal_observation(
            stored,
            mapping=mapping(MODEL_A),
            period_start=END - timedelta(days=6),
            period_end=END,
        )


def test_persisted_count_requires_operational_provenance_and_matching_receipt():
    closed = receipt(END, ("one",), country="Spain")
    issued = datetime.combine(END, time(), UTC)
    normalized = NormalizedOperationalEvent(
        provider=EVENTS.provider,
        source_record_id="one",
        event_type=EVENTS.metric,
        event_date=issued,
        retrieved_at=closed.completed_at,
        country="Kingdom of Spain",
    )
    stored = Event(
        id=uuid4(),
        source_record_id="one",
        event_type=EVENTS.metric,
        occurred_at=issued,
        created_at=closed.available_at,
        provenance=normalized.model_dump(mode="json"),
    )
    assert event_count_observation([stored], receipt=closed).value == 1
    stored.provenance.pop("temporal_classification")
    with pytest.raises(ValueError, match="operational provenance"):
        event_count_observation([stored], receipt=closed)


@pytest.fixture
def advisory_db():
    url = os.getenv("POSTGRES_TEST_URL")
    if not url:
        pytest.skip("POSTGRES_TEST_URL requires a disposable PostgreSQL database")
    engine = create_engine(url)
    with engine.connect() as connection:
        assert connection.dialect.name == "postgresql"
    # Each test owns a schema and logs in as a distinct non-owner role.
    schema = f"ew_test_{uuid4().hex}"
    role = f"{schema}_login"
    password = uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
        metadata.create_all(connection.execution_options(schema_translate_map={None: schema}))
        connection.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD '{password}'"))
        connection.execute(text(f"GRANT USAGE ON SCHEMA {schema} TO {role}"))
        connection.execute(
            text(f"GRANT SELECT, INSERT ON {schema}.early_warning_history TO {role}")
        )
        connection.execute(
            text(f"GRANT SELECT, INSERT, UPDATE ON {schema}.early_warning_checkpoints TO {role}")
        )
    runtime = create_engine(
        engine.url.set(username=role, password=password),
        execution_options={"schema_translate_map": {None: schema}},
    )
    try:
        yield runtime
    finally:
        runtime.dispose()
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
            connection.execute(text(f"DROP ROLE {role}"))
        engine.dispose()


def persist(connection, rows, *, feeds=(MODEL_A,), end=END, as_of=END, cutoff=END, replay_id=None):
    return persist_evaluation(
        connection,
        scope(*feeds),
        rows,
        thresholds=Thresholds(),
        period_end=end,
        as_of=as_of,
        revision_cutoff=cutoff,
        replay_id=replay_id,
    )


def test_postgres_concurrent_retry_and_reordered_feeds(advisory_db):
    rows = samples(MODEL_A, [0.25, 0.25, 0.40]) + samples(MODEL_B, [0.20] * 3)
    ready = Barrier(2)

    def retry(feeds):
        with advisory_db.begin() as connection:
            ready.wait(timeout=10)
            return persist(connection, rows, feeds=feeds)

    with ThreadPoolExecutor(2) as executor:
        a = executor.submit(retry, (MODEL_A, MODEL_B))
        b = executor.submit(retry, (MODEL_B, MODEL_A))
        first, second = a.result(timeout=15), b.result(timeout=15)
    assert first == second
    assert first.event_id == assess(rows, feeds=(MODEL_A, MODEL_B))[0].event_id
    assert first.event_id
    with advisory_db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(history)) == 1
        assert connection.scalar(select(func.count()).select_from(checkpoints)) == 1


def test_postgres_rollback_and_replay_are_isolated(advisory_db):
    rows = samples(MODEL_A, [0.25, 0.25, 0.40])
    with pytest.raises(RuntimeError, match="abort"):
        with advisory_db.begin() as connection:
            uncommitted = persist(connection, rows)
            assert uncommitted.event_id
            raise RuntimeError("abort")
    with advisory_db.begin() as connection:
        assert connection.scalar(select(func.count()).select_from(history)) == 0
        assert connection.scalar(select(func.count()).select_from(checkpoints)) == 0
        replay = persist(connection, rows, replay_id="audit")
        live = persist(connection, rows)
        assert replay.level == live.level == Level.WARNING
        assert replay.event_id is None
        assert live.event_id == uncommitted.event_id
    with advisory_db.connect() as connection:
        assert set(connection.scalars(select(history.c.namespace))) == {"live", "replay:audit"}


def test_postgres_late_evidence_appends_without_changing_prior_occurrence(advisory_db):
    rows = samples(MODEL_A, [0.25, 0.25, 0.40])
    tomorrow = END + timedelta(days=1)
    late = rows[-1].model_copy(update={"available_on": tomorrow})
    with advisory_db.begin() as connection:
        missing = persist(connection, [*rows[:-1], late])
        assert missing.level == Level.INSUFFICIENT_DATA
        revised = persist(connection, [*rows[:-1], late], as_of=tomorrow, cutoff=tomorrow)
        assert revised.level == Level.WARNING and revised.event_id
    with advisory_db.begin() as connection:
        retry = persist(connection, rows)
        assert retry == missing
        assert connection.scalar(select(func.count()).select_from(history)) == 2
        assert connection.scalar(select(func.count(history.c.event_id))) == 1


@pytest.mark.parametrize(
    ("feed", "values", "indicator"),
    [
        (MODEL_A, [0.25, 0.25, 0.40], "forecast_jump"),
        (MODEL_A, [0.20, 0.225, 0.30], "sustained_deterioration"),
        (MODEL_A, [0.10, 0.10, 0.20], "emerging_risk"),
        (EVENTS, [5, 5, 10], "activity_jump"),
        (EVENTS, [3, 5, 8], "sustained_activity_increase"),
    ],
)
def test_exact_thresholds_are_inclusive(feed, values, indicator):
    record, _ = assess(samples(feed, values), feeds=(feed,))
    assert indicator in indicators(record)


def test_below_jump_threshold_stays_normal():
    record, _ = assess(samples(MODEL_A, [0.25, 0.25, 0.399999]))
    assert record.level == Level.NORMAL
    assert record.event_id is None


def test_both_model_diagnostics_are_retained():
    rows = samples(MODEL_A, [0.10, 0.10, 0.30]) + samples(MODEL_B, [0.80, 0.80, 0.60])
    record, _ = assess(rows, feeds=(MODEL_A, MODEL_B))
    assert {"model_disagreement", "opposing_model_movements"} <= indicators(record)


def test_receipt_cannot_certify_historical_or_unclosed_windows():
    valid = receipt(END).model_dump()
    with pytest.raises(ValueError, match="recent_operational"):
        OperationalReceipt.model_validate({**valid, "temporal_classification": "annual_ged"})
    with pytest.raises(ValueError, match="closed window"):
        OperationalReceipt.model_validate(
            {**valid, "completed_at": datetime.combine(END, time(), UTC)}
        )


def test_postgres_caught_failure_leaves_no_checkpoint(advisory_db):
    with advisory_db.begin() as connection:
        with pytest.raises(ValueError, match="revision cutoff"):
            persist(connection, [], cutoff=END + timedelta(days=1))
    with advisory_db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(checkpoints)) == 0
        assert connection.scalar(select(func.count()).select_from(history)) == 0


def test_activity_corroboration_requires_review_of_the_exact_feed_and_target():
    unrelated = Feed(provider=EVENTS.provider, metric="Public demonstrations")
    forecast_rows = samples(MODEL_A, [0.25, 0.25, 0.44])
    activity_rows = samples(EVENTS, [1, 2, 11])
    unreviewed_rows = samples(unrelated, [1, 2, 11])
    original = scope(MODEL_A, EVENTS)
    values = original.model_dump()
    reviewed = values["activity_mappings"][0]
    for settings, message in (
        ({"activity_mappings": ()}, "one versioned reviewed"),
        ({"activity_mappings": ({**reviewed, "target": "political_violence"},)}, "same target"),
        ({"activity_mappings": ({**reviewed, "version": ""},)}, "at least 1"),
        ({"activity_mappings": ({**reviewed, "review_ref": ""},)}, "at least 1"),
        ({"feeds": (MODEL_A, unrelated)}, "one versioned reviewed"),
    ):
        with pytest.raises(ValueError, match=message):
            Scope.model_validate({**values, **settings})
    record, _ = assess(forecast_rows + unreviewed_rows, feeds=(MODEL_A,))
    assert record.level == Level.WARNING
    record, _ = assess(forecast_rows + unreviewed_rows, feeds=(MODEL_A, EVENTS))
    assert record.level == Level.INSUFFICIENT_DATA
    record, state = assess(forecast_rows + activity_rows, feeds=(MODEL_A, EVENTS))
    assert record.level == Level.CRITICAL
    updated = Scope.model_validate({**values, "activity_mappings": ({**reviewed, "version": "2"},)})
    with pytest.raises(ValueError, match="previous state must match"):
        evaluate(
            updated,
            forecast_rows + activity_rows,
            previous=state,
            as_of=record.as_of,
            period_end=END,
        )


def test_operational_receipt_is_bound_to_collection_filter_country_and_window():
    verified = receipt(END)
    for update in (
        {"provider": "other"},
        {"event_type": "Other"},
        {"country": "Elsewhere"},
        {"period_start": verified.period_start - WEEK},
        {"period_end": END + WEEK},
        {"collection_id": "other-collection"},
    ):
        reused = verified.model_copy(update=update)
        with pytest.raises(ValueError, match="receipt ID must bind"):
            Observation.from_events([], receipt=reused)
    assert Observation.from_events([], receipt=verified).value == 0


def test_complete_status_cannot_replace_an_exact_operational_audit():
    verified = receipt(END)
    audit = verified.attestation
    with pytest.raises(ValueError, match="verified_complete"):
        OperationalReceipt.model_validate(
            {**verified.model_dump(), "status": "complete_empty", "attestation": None}
        )
    for proof in (
        None,
        audit.model_copy(update={"query": audit.query.model_copy(update={"event_type": "All"})}),
        audit.model_copy(
            update={
                "query": audit.query.model_copy(
                    update={"period_start": verified.period_start - WEEK}
                )
            }
        ),
    ):
        with pytest.raises(ValueError, match="audit of the exact operational query"):
            Observation.from_events([], receipt=verified.model_copy(update={"attestation": proof}))
    for update in (
        {"kind": "historical_release"},
        {"kind": "media"},
        {"pagination_exhausted": False},
        {"unrestricted": False},
        {"counts_reconciled": False},
    ):
        with pytest.raises(ValueError):
            Observation.from_events(
                [],
                receipt=verified.model_copy(
                    update={"attestation": audit.model_copy(update=update)}
                ),
            )
    derived = sample(EVENTS, END, 0)
    invalid = derived.model_copy(
        update={"receipt": verified.model_copy(update={"attestation": None})}
    )
    with pytest.raises(ValueError, match="audit of the exact operational query"):
        assess([*samples(EVENTS, [0, 0, 0])[:-1], invalid], feeds=(EVENTS,))


@pytest.mark.parametrize("boolean", [True, False])
def test_boolean_observation_rejected_even_with_validation_bypass(boolean):
    rows = samples(MODEL_A, [0.0, 0.0, 1.0])
    with pytest.raises(ValueError, match="Boolean"):
        Observation.model_validate({**rows[-1].model_dump(), "value": boolean})
    with pytest.raises(ValueError, match="Boolean"):
        assess([*rows[:-1], rows[-1].model_copy(update={"value": boolean})])
    assert assess(rows)[0].level == Level.WARNING


def test_postgres_runtime_login_resumes_checkpoint_and_cannot_mutate_history(advisory_db):
    rows = samples(MODEL_A, [0.25, 0.25, 0.40, 0.40, 0.40], end=END + 2 * WEEK)
    with advisory_db.begin() as connection:
        assert connection.scalar(text("SELECT current_user")).startswith("ew_test_")
        assert not connection.scalar(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        )
        initial = persist(connection, rows)
        assert initial.event_id
    for offset, expected in ((1, Level.WARNING), (2, Level.NORMAL)):
        day = END + offset * WEEK
        with advisory_db.begin() as connection:
            record = persist(connection, rows, end=day, as_of=day, cutoff=day)
            assert record.level == expected
            assert record.event_id is None
    with advisory_db.begin() as connection, pytest.raises(ProgrammingError, match="permission"):
        with connection.begin_nested():
            connection.execute(history.delete())
    with advisory_db.begin() as connection:
        assert connection.scalar(select(func.count(history.c.event_id))) == 1


def test_postgres_migration_install_upgrade_and_rollback():
    url = os.getenv("POSTGRES_TEST_URL")
    if not url:
        pytest.skip("POSTGRES_TEST_URL requires a disposable PostgreSQL database")
    owner = create_engine(url, isolation_level="AUTOCOMMIT")
    name = f"ew_migration_{uuid4().hex}"
    with owner.connect() as connection:
        assert connection.dialect.name == "postgresql"
        connection.execute(text(f"CREATE DATABASE {name}"))
    database = create_engine(owner.url.set(database=name))
    env = {**os.environ, "DATABASE_URL": database.url.render_as_string(hide_password=False)}

    def migrate(command, revision):
        subprocess.run([sys.executable, "-m", "alembic", command, revision], env=env, check=True)

    try:
        migrate("upgrade", "head")
        tables = set(inspect(database).get_table_names())
        assert {"early_warning_history", "early_warning_checkpoints", "forecasts"} <= tables
        with database.begin() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "include_name": lambda name, kind, _: kind != "table" or name in metadata.tables
                },
            )
            assert compare_metadata(context, metadata) == []
            assert persist(connection, samples(MODEL_A, [0.25, 0.25, 0.40])).event_id
        migrate("downgrade", "0008")
        assert set(inspect(database).get_table_names()) == tables - {
            "early_warning_history",
            "early_warning_checkpoints",
        }
        migrate("upgrade", "head")
        assert set(inspect(database).get_table_names()) == tables
        with database.begin() as connection:
            assert connection.scalar(select(func.count()).select_from(history)) == 0
    finally:
        database.dispose()
        with owner.connect() as connection:
            connection.execute(text(f"DROP DATABASE {name}"))
        owner.dispose()
