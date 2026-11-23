import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import ArgumentError, OperationalError
from sqlalchemy.orm import Session

from geointel.domain.models import (
    AnalysisRun,
    Event,
    Forecast,
    ForecastSignal,
    KnowledgeWork,
    NewsReport,
    StrategicAnalysis,
    StrategicClaim,
)
from geointel.domain.schemas import (
    AnalysisRequest,
    NormalizedForecastSignal,
    NormalizedNewsReport,
    NormalizedOperationalEvent,
)
from geointel.knowledge.ingestion import KnowledgeIngestor
from geointel.pipeline.service import AnalysisPipeline
from geointel.providers.base import ModelRouter
from geointel.providers.offline import OfflineModel


@pytest.fixture(scope="module")
def postgres_engine():
    url = os.getenv("POSTGRES_TEST_URL")
    if not url:
        pytest.skip(
            "POSTGRES_TEST_URL is unset. Set it to a migrated disposable PostgreSQL test database."
        )
    try:
        engine = create_engine(url)
    except ArgumentError:
        pytest.fail("POSTGRES_TEST_URL must be a valid SQLAlchemy PostgreSQL URL.", pytrace=False)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("POSTGRES_TEST_URL must point to PostgreSQL.", pytrace=False)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session(postgres_engine):
    try:
        connection = postgres_engine.connect()
    except OperationalError:
        pytest.fail(
            "Could not connect using POSTGRES_TEST_URL. Check service health, host, port, "
            "database and credentials.",
            pytrace=False,
        )
    with connection:
        # Session commits release savepoints. Closing the connection rolls back the test.
        connection.begin()
        with Session(
            connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session


def test_postgres_repeated_persistence_and_forecast_immutability(session):
    model = OfflineModel()
    request = AnalysisRequest(
        location="Spain",
        question="Assess organized political violence in Spain for the next twelve months.",
        horizon_months=12,
    )
    pipeline = AnalysisPipeline(session, ModelRouter(model, model, model))
    first = pipeline.run(request)
    second = pipeline.run(request)
    assert first.id != second.id
    run_ids = [first.id, second.id]
    assert session.query(AnalysisRun).filter(AnalysisRun.id.in_(run_ids)).count() == 2
    assert session.query(Forecast).filter(Forecast.analysis_run_id.in_(run_ids)).count() == 8
    forecast = session.scalar(select(Forecast).where(Forecast.analysis_run_id == first.id))
    forecast.rationale = "forbidden mutation"
    with pytest.raises(ValueError, match="immutable"):
        session.commit()


def test_postgres_operational_event_and_predictive_signal_persistence(session):
    class OperationalFixtures:
        connector_name = "ACLED"

        def collect(self, location, horizon_months):
            now = datetime.now(UTC)
            return [
                NormalizedOperationalEvent(
                    source_record_id="synthetic-postgres-event",
                    event_date=now,
                    event_type="Synthetic test event",
                    country=location,
                    retrieved_at=now,
                    provenance={"synthetic_fixture": True},
                ),
                NormalizedForecastSignal(
                    provider="CAST",
                    source_record_id="synthetic-postgres-signal",
                    model_name="synthetic-test-model",
                    geographic_unit="country",
                    location=location,
                    issue_date=now,
                    target_start=now,
                    target_end=now + timedelta(days=30),
                    horizon_months=1,
                    target_variable="synthetic_test_target",
                    prediction=1.0,
                    unit="provider_native_units",
                    retrieved_at=now,
                    provenance={"synthetic_fixture": True, "predictive_not_observed": True},
                ),
            ]

    model = OfflineModel()
    request = AnalysisRequest(
        location="Spain",
        question="Assess organized political violence in Spain for the next twelve months.",
        horizon_months=12,
    )
    pipeline = AnalysisPipeline(session, ModelRouter(model, model, model), [OperationalFixtures()])
    run = pipeline.run(request)
    assert (
        session.query(Event)
        .filter_by(analysis_run_id=run.id, source_record_id="synthetic-postgres-event")
        .count()
        == 1
    )
    assert (
        session.query(ForecastSignal)
        .filter_by(
            analysis_run_id=run.id, source_record_id="synthetic-postgres-signal", provider="CAST"
        )
        .count()
        == 1
    )


def test_postgres_news_report_persistence_remains_separate(session):
    class NewsFixture:
        connector_name = "GDELT"

        def collect(self, location, horizon_months):
            del horizon_months
            now = datetime.now(UTC)
            return [
                NormalizedNewsReport(
                    source_record_id="synthetic-news-id",
                    canonical_url="https://example.invalid/synthetic-news",
                    title="Synthetic media report",
                    retrieval_timestamp=now,
                    requested_geography=location,
                    provenance={"synthetic_fixture": True},
                )
            ]

    request = AnalysisRequest(
        location="Spain",
        question="Assess organized political violence in Spain for the next twelve months.",
        horizon_months=12,
    )
    model = OfflineModel()
    run = AnalysisPipeline(session, ModelRouter(model, model, model), [NewsFixture()]).run(request)
    assert (
        session.query(NewsReport)
        .filter_by(analysis_run_id=run.id, source_record_id="synthetic-news-id")
        .count()
        == 1
    )
    assert (
        session.query(Event)
        .filter_by(analysis_run_id=run.id, source_record_id="synthetic-news-id")
        .count()
        == 0
    )


def test_postgres_strategic_knowledge_relationships_and_analysis_audit(session):
    fixture = Path(__file__).parent / "fixtures" / "synthetic_knowledge.json"
    payload = json.loads(fixture.read_text())
    model = OfflineModel()
    if not session.scalar(
        select(KnowledgeWork).where(KnowledgeWork.external_id == payload["work"]["id"])
    ):
        KnowledgeIngestor(session).ingest(payload)
        session.commit()
    claim = session.scalar(
        select(StrategicClaim).where(StrategicClaim.external_id == "kissinger-diplomacy-001")
    )
    assert {item.slug for item in claim.concepts} == {"diplomatic-flexibility"}
    run = AnalysisPipeline(session, ModelRouter(model, model, model)).run(
        AnalysisRequest(
            location="Testland",
            question="Assess balance of power and diplomatic flexibility over twelve months.",
            horizon_months=12,
        )
    )
    audit = session.scalar(
        select(StrategicAnalysis).where(StrategicAnalysis.analysis_run_id == run.id)
    )
    assert audit.retrieved_claim_ids
    assert audit.retrieval_provenance


def test_postgres_validation_audit_linkage_and_repeated_history(session):
    from geointel.domain.models import ValidationResult, ValidationRun
    from geointel.validation.runner import ValidationRunner

    first = ValidationRunner(session).run(case_id="spain")["cases"][0]
    second = ValidationRunner(session).run(case_id="spain")["cases"][0]
    assert first["validation_run_id"] != second["validation_run_id"]
    rows = list(session.scalars(select(ValidationRun).where(ValidationRun.case_id == "spain")))
    assert len(rows) >= 2
    assert all(row.analysis_run_id for row in rows)
    assert session.query(ValidationResult).count() >= 2 * 20


def test_postgres_monitoring_linkage_alert_dedupe_and_resolution(session):
    from uuid import uuid4

    from geointel.domain.models import Alert, DetectedChange, MonitoringRun
    from geointel.monitoring import AlertEngine, MonitoringService

    model = OfflineModel()
    service = MonitoringService(
        session, lambda: AnalysisPipeline(session, ModelRouter(model, model, model))
    )
    token = uuid4().hex
    target = service.add_target(
        service.create_watchlist(f"Synthetic PostgreSQL {token}"),
        f"SYN-{token}",
        f"Synthetic {token}",
    )
    baseline = service.run_target(target)
    repeated = service.run_target(target)
    assert (
        baseline.analysis_run_id and repeated.previous_analysis_run_id == baseline.analysis_run_id
    )
    change = DetectedChange(
        monitoring_run_id=repeated.id,
        change_type="forecast_change",
        previous_state={"value": "synthetic-before"},
        current_state={"value": "synthetic-after"},
        affected_categories=["major_political_violence"],
        source_references=["synthetic:test"],
        severity="material",
        material=True,
        explanation="Synthetic structured transition.",
        provenance={"synthetic_fixture": True},
    )
    session.add(change)
    session.flush()
    engine_alerts = AlertEngine()
    first = engine_alerts.evaluate(
        session, target, repeated, [change], {}, repeated.source_availability
    )
    session.flush()
    duplicate = engine_alerts.evaluate(
        session, target, repeated, [change], {}, repeated.source_availability
    )
    assert first.id == duplicate.id
    engine_alerts.resolve(session, first)
    session.commit()
    assert session.scalar(select(Alert).where(Alert.id == first.id)).status == "resolved"
    assert session.scalar(
        select(MonitoringRun).where(MonitoringRun.id == repeated.id)
    ).analysis_run_id


def test_postgres_historical_summary_and_raw_provenance(session):
    from test_historical_base_rates import observation

    from geointel.domain.models import Evidence

    class History:
        def collect(self, location, horizon_months):
            return [observation("postgres-history", 2020, 2, 1, 3)]

    model = OfflineModel()
    run = AnalysisPipeline(session, ModelRouter(model, model, model), [History()]).run(
        AnalysisRequest(
            location="Spain",
            question="Assess organized violence over twelve months.",
            horizon_months=12,
        )
    )
    session.expire_all()
    saved = session.get(AnalysisRun, run.id)
    summary = saved.collection_metadata["historical_base_rate_summary"]
    profile = saved.collection_metadata["historical_conflict_profile"]
    assert profile == saved.analyst_output["historical_conflict_profile"]
    assert profile["overall"]["fatality_statistics"]["best_total"] == 2
    assert profile["normalization_audit"][0]["source_record_id"] == "postgres-history"
    assert profile["annualized_observation_rate"] is None
    assert summary["fatality_statistics"]["best_total"] == 2
    assert summary["coverage"][0]["coverage_end"] == "2025-12-31"
    assert not saved.collection_metadata["current_operational_coverage_available"]
    assert saved.analyst_output["observed_evidence"] == []
    assert (
        session.scalar(select(Evidence).where(Evidence.analysis_run_id == run.id)).provenance[
            "temporal_role"
        ]
        == "annual_historical"
    )


def test_postgres_collection_coverage_json_round_trip(session):
    from geointel.connectors.base import DisabledConnector
    from geointel.coverage import CoverageDecision

    model = OfflineModel()
    pipeline = AnalysisPipeline(
        session, ModelRouter(model, model, model), [DisabledConnector("ACLED")]
    )
    request = AnalysisRequest(location="Spain", question="Assess conflict risks", horizon_months=12)
    run_id = pipeline.run(request).id
    session.expunge_all()
    persisted = session.get(AnalysisRun, run_id).collection_metadata
    assert CoverageDecision.from_metadata(persisted).projection("ACLED")["state"] == "not_attempted"
    assert persisted["collection_coverage"]["collections"][0]["event_counts"]["confirmed"] is None
    assert persisted["connector_outcomes"][0]["status"] == "disabled"
