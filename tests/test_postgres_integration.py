import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import ArgumentError, OperationalError
from sqlalchemy.orm import Session

from geointel.api.app import dashboard_app
from geointel.domain.database import get_session
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
from geointel.search import IntelligenceSearch, RecordType, SearchQuery


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


def test_postgres_operational_event_and_predictive_signal_persistence(session, monkeypatch):
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

    monkeypatch.setitem(dashboard_app.dependency_overrides, get_session, lambda: session)
    with TestClient(dashboard_app) as client:
        for route, record_id in (
            ("observations", "synthetic-postgres-event"),
            ("forecasts", "synthetic-postgres-signal"),
        ):
            response = client.get(f"/api/v1/dashboard/{route}?country=ES")
            assert response.status_code == 200
            assert any(
                item["provenance"]["source_record_id"] == record_id
                for item in response.json()["items"]
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


def test_postgres_historical_summary_and_raw_provenance(session, monkeypatch):
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

    monkeypatch.setitem(dashboard_app.dependency_overrides, get_session, lambda: session)
    with TestClient(dashboard_app) as client:
        response = client.get("/api/v1/dashboard/ucdp-observations?country=ES")
        assert response.status_code == 200
        (record,) = response.json()["items"]
        assert record["temporal_role"] == "annual_historical"
        assert record["provenance"]["source_record_id"] == "postgres-history"


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


def test_postgres_empty_and_failed_historical_collections_are_diagnostic(session):
    from uuid import uuid4

    import httpx

    from geointel.connectors.ucdp import UCDPConnector
    from geointel.domain.models import Alert
    from geointel.domain.schemas import Confidence, SynthesisOutput
    from geointel.monitoring import MonitoringService

    class RoutedModel(OfflineModel):
        fail = False

        def generate(self, role, payload, output_type):
            result = super().generate(role, payload, output_type)
            if output_type is SynthesisOutput:
                result.assessments[0].confidence = Confidence.HIGH if self.fail else Confidence.LOW
            return result

    model = RoutedModel()

    def response(_):
        if model.fail:
            return httpx.Response(503)
        return httpx.Response(200, json={"TotalPages": 0, "TotalCount": 0, "Result": []})

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        connector = UCDPConnector(
            "https://example.test",
            "25.1",
            client=client,
            official_api=True,
            access_token="fixture",
            retries=0,
        )
        connectors = []
        svc = MonitoringService(
            session, lambda: AnalysisPipeline(session, ModelRouter(model, model, model), connectors)
        )
        target = svc.add_target(svc.create_watchlist(uuid4().hex), "ESP", "Spain")
        svc.run_target(target)
        model.fail = True
        svc.run_target(target)
        alerts = select(Alert).where(Alert.target_id == target.id)
        existing = session.scalars(alerts).one()
        last_seen = existing.last_observed_at

        connectors.append(connector)
        for failed in (False, True, False, True):
            model.fail = failed
            run = svc.run_target(target)
            assert run.status == "completed"
            receipt = run.analysis_run.collection_metadata["collection_coverage"]["collections"][0]
            assert receipt["state"] == ("failed" if failed else "complete_empty")
            assert not run.analysis_run.collection_metadata["historical_observation_count"]
            assert all(not change.material for change in run.changes)
            assert session.scalars(alerts).one().last_observed_at == last_seen

        class Operational:
            failed = False

            def __init__(self, name):
                self.connector_name = name

            def collect(self, location, horizon_months):
                if self.failed:
                    raise RuntimeError("synthetic operational outage")
                return []

        acled, views = Operational("ACLED"), Operational("VIEWS")
        connectors.extend([acled, views])
        svc.run_target(target)
        acled.failed = views.failed = True
        outage = svc.run_target(target)
        operational_alert = session.scalars(
            alerts.where(Alert.monitoring_run_id == outage.id)
        ).one()
        last_operational_seen = operational_alert.last_observed_at
        for failed in (False, True):
            model.fail = failed
            repeated = svc.run_target(target)
            assert all(not change.material for change in repeated.changes)
        assert len(session.scalars(alerts).all()) == 2
        assert operational_alert.last_observed_at == last_operational_seen


def test_postgres_concurrent_target_and_failed_finalization(postgres_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4

    from sqlalchemy.schema import CreateSchema, DropSchema

    from geointel.domain.models import Alert, Base, MonitoringRun, WatchlistTarget
    from geointel.domain.schemas import Confidence, SynthesisOutput
    from geointel.monitoring import AlertEngine, MonitoringService

    schema = f"monitoring_{uuid4().hex}"
    with postgres_engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = postgres_engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(isolated)
        rendezvous = Barrier(2, timeout=15)

        class RoutedModel(OfflineModel):
            high = False

            def generate(self, role, payload, output_type):
                result = super().generate(role, payload, output_type)
                if output_type is SynthesisOutput:
                    result.assessments[0].confidence = (
                        Confidence.HIGH if self.high else Confidence.LOW
                    )
                return result

        class ConcurrentPipeline(AnalysisPipeline):
            def run(self, request):
                result = super().run(request)
                rendezvous.wait()
                return result

        class FailingAlertEngine(AlertEngine):
            def evaluate(self, session, *args):
                assert super().evaluate(session, *args) is not None
                session.flush()
                raise RuntimeError("injected failure after alert flush")

        with Session(isolated) as owner:
            model = RoutedModel()
            router = ModelRouter(model, model, model)
            svc = MonitoringService(owner, lambda: AnalysisPipeline(owner, router))
            target = svc.add_target(svc.create_watchlist("Concurrent fixture"), "ESP", "Spain")
            target_id = target.id

            def run_concurrently():
                with Session(isolated) as worker:
                    worker_model = RoutedModel()
                    worker_router = ModelRouter(worker_model, worker_model, worker_model)
                    monitoring = MonitoringService(
                        worker, lambda: ConcurrentPipeline(worker, worker_router)
                    )
                    return monitoring.run_target(worker.get(WatchlistTarget, target_id)).id

            with ThreadPoolExecutor(max_workers=2) as pool:
                ids = list(pool.map(lambda _: run_concurrently(), range(2)))
            runs = [owner.get(MonitoringRun, run_id) for run_id in ids]
            first, second = sorted(runs, key=lambda run: run.completed_at)
            assert first.status == second.status == "completed", [run.error_reason for run in runs]
            assert first.baseline_established and not second.baseline_established
            assert second.previous_monitoring_run_id == first.id
            owner.refresh(target)
            schedule = target.next_due_at

            model.high = True
            svc.alert_engine = FailingAlertEngine()
            failed = svc.run_target(target)
            assert failed.status == "failed"
            assert failed.error_reason == "injected failure after alert flush"
            assert failed.analysis_run.status == "completed"
            assert len(failed.analysis_run.forecasts) == 4
            assert not failed.changes
            assert owner.scalars(select(Alert)).all() == []
            assert target.next_due_at == schedule

            svc.alert_engine = AlertEngine()
            recovered = svc.run_target(target)
            assert recovered.previous_monitoring_run_id == second.id
            assert owner.scalars(select(Alert)).one().monitoring_run_id == recovered.id
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))


def test_postgres_search_missing_relation_preserves_transaction(session):
    # Simulate an unmigrated relation within the rollback-isolated test transaction.
    session.execute(text("ALTER TABLE events RENAME TO events_unavailable"))
    page = IntelligenceSearch(session).search(
        SearchQuery(record_types=(RecordType.EVENT, RecordType.SIGNAL))
    )
    assert not page.complete
    assert [(source.record_type, source.status) for source in page.sources] == [
        (RecordType.EVENT, "unavailable"),
        (RecordType.SIGNAL, "available"),
    ]
    assert session.scalar(select(Forecast.id).limit(1)) is None
