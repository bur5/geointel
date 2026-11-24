from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from geointel.domain.models import AnalysisRun, Base, Event, ForecastSignal, Location, Source
from geointel.monitoring.data_quality import source_health_report

AS_OF = datetime(2026, 11, 23, 12, tzinfo=UTC)
COLLECTED = AS_OF - timedelta(days=1)


def outcome(provider, **fields):
    return {
        "connector": provider,
        "status": "succeeded",
        "succeeded": True,
        "record_count": 1,
        "collection_timestamp": COLLECTED.isoformat(),
        **fields,
    }


@pytest.fixture
def snapshot():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        location = Location(name="Spain")
        acled = Source(name="ACLED", source_type="operational_events")
        session.add_all([location, acled])
        session.flush()
        run = AnalysisRun(
            location=location,
            question="Example",
            horizon_months=12,
            status="completed",
            completed_at=COLLECTED + timedelta(minutes=1),
            provider_config={},
            pipeline_version="test",
            collection_metadata={
                "connector_outcomes": [outcome(name) for name in ("ACLED", "VIEWS", "CAST")]
            },
        )
        observed = Event(
            analysis_run=run,
            source_id=acled.id,
            location_id=location.id,
            source_record_id="event-1",
            event_type="Battles",
            occurred_at=COLLECTED,
            description="Test event",
            confidence="reported",
            provenance={"country": "Kingdom of Spain", "retrieved_at": COLLECTED.isoformat()},
        )
        views, cast = [
            ForecastSignal(
                analysis_run=run,
                provider=name,
                source_record_id="same-id",
                location_id=location.id,
                model_name=name,
                geographic_unit="country",
                source_location="Spain",
                issue_date=COLLECTED - timedelta(days=7),
                target_start=AS_OF + timedelta(days=1),
                target_end=AS_OF + timedelta(days=31),
                target_variable="event_count",
                prediction=0,
                retrieved_at=COLLECTED,
                alignment_status="aligned",
                alignment_notes=[],
                provenance={},
            )
            for name in ("VIEWS", "CAST")
        ]
        session.add_all([run, observed, views, cast])
        session.commit()
        yield session, run, observed, views, cast
    engine.dispose()


def findings(report):
    return {finding["code"]: finding["count"] for finding in report["findings"]}


def test_normal_snapshot_is_deterministic_and_read_only(snapshot):
    session, run, *_ = snapshot
    run_id = run.id
    session.expunge_all()
    statements = []

    @event.listens_for(session.bind, "before_cursor_execute")
    def record_statement(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    session.add(Location(name="Pending change"))
    report = source_health_report(session, run_id, as_of=AS_OF)
    assert report == source_health_report(session, run_id, as_of=AS_OF)
    assert report["schema_version"] == 1
    assert {item["status"] for item in report["sources"].values()} == {"healthy"}
    assert report["sources"]["ACLED"]["freshness"]["age_seconds"] == 86400
    assert report["sources"]["ForecastSignal"]["coverage"]["usable_record_count"] == 2
    assert "risk" not in report
    assert statements and all(statement.startswith("SELECT") for statement in statements)
    assert len(session.new) == 1


def test_duplicate_invalid_and_geographically_inconsistent_rows(snapshot):
    session, run, observed, views, _ = snapshot
    session.add(
        Event(
            analysis_run=run,
            source_id=observed.source_id,
            location_id=observed.location_id,
            source_record_id=observed.source_record_id,
            event_type="Battles",
            description="Duplicate",
            confidence="reported",
            occurred_at=AS_OF + timedelta(days=1),
            provenance={"country": "Nigeria", "retrieved_at": "invalid"},
        )
    )
    views.target_start = views.target_end + timedelta(days=1)
    session.commit()

    sources = source_health_report(session, run.id, as_of=AS_OF)["sources"]
    assert sources["ACLED"]["status"] == "degraded"
    assert findings(sources["ACLED"]) == {
        "duplicate_records": 1,
        "geography_mismatch": 1,
        "invalid_timestamp": 1,
        "record_count_mismatch": 1,
    }
    assert sources["VIEWS"]["status"] == "unavailable"
    assert findings(sources["VIEWS"])["invalid_timestamp"] == 1
    assert sources["ForecastSignal"]["status"] == "degraded"


def test_stale_age_and_expired_forecast_coverage(snapshot):
    session, run, _, _, cast = snapshot
    cast.target_start = COLLECTED - timedelta(days=3)
    cast.target_end = COLLECTED
    session.commit()
    sources = source_health_report(
        session, run.id, as_of=AS_OF, freshness_days={"ACLED": 1, "VIEWS": 7}
    )["sources"]
    assert sources["ACLED"]["status"] == "healthy"
    assert sources["VIEWS"]["status"] == "stale"
    assert sources["CAST"]["status"] == "stale"
    assert findings(sources["CAST"]) == {"expired_target_coverage": 1}
    assert sources["ForecastSignal"]["status"] == "stale"


def test_unavailable_sources_do_not_look_healthy(snapshot):
    session, run, observed, views, _ = snapshot
    session.delete(observed)
    session.delete(views)
    run.collection_metadata = {
        "connector_outcomes": [
            outcome("ACLED", record_count=0),
            outcome("CAST", collection_audit={"status": "FAILED", "duplicates": 0, "rejected": 0}),
        ]
    }
    session.commit()

    sources = source_health_report(session, run.id, as_of=AS_OF)["sources"]
    assert {item["status"] for item in sources.values()} == {"unavailable"}
    assert findings(sources["ACLED"]) == {"missing_usable_records": 1}
    assert findings(sources["VIEWS"])["missing_outcome"] == 1
    assert findings(sources["CAST"])["collection_audit_unavailable"] == 1


def test_collection_telemetry_detects_filtered_records(snapshot):
    session, run, _, _, _ = snapshot
    audit = {"status": "PARTIAL", "rejected": 2, "duplicates": 3, "truncated": True}
    run.collection_metadata = {
        "connector_outcomes": [
            outcome("ACLED", collection_audit=audit),
            outcome("VIEWS", duplicates_removed=1),
            outcome("CAST"),
        ]
    }
    session.commit()
    sources = source_health_report(session, run.id, as_of=AS_OF)["sources"]
    assert sources["ACLED"]["status"] == sources["VIEWS"]["status"] == "degraded"
    assert findings(sources["ACLED"]) == {
        "duplicate_records": 3,
        "incomplete_collection": 1,
        "rejected_records": 2,
    }
    assert findings(sources["VIEWS"]) == {"duplicate_records": 1}


def test_invalid_request_cannot_return_healthy(snapshot):
    session, run, *_ = snapshot
    with pytest.raises(ValueError, match="completed analysis"):
        source_health_report(session, uuid4(), as_of=AS_OF)
    with pytest.raises(ValueError, match="timezone-aware"):
        source_health_report(session, run.id, as_of=AS_OF.replace(tzinfo=None))
    with pytest.raises(ValueError, match="by as_of"):
        source_health_report(session, run.id, as_of=COLLECTED)
    with pytest.raises(ValueError, match="positive whole days"):
        source_health_report(session, run.id, as_of=AS_OF, freshness_days={"CAST": 0})
    run.collection_metadata = {"connector_outcomes": [None]}
    with pytest.raises(ValueError, match="malformed connector outcomes"):
        source_health_report(session, run.id, as_of=AS_OF)
