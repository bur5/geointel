import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from geointel.domain.models import AnalysisRun, Event, Forecast, ForecastSignal
from geointel.domain.schemas import (
    AnalysisRequest,
    NormalizedForecastSignal,
    NormalizedOperationalEvent,
)
from geointel.pipeline.service import AnalysisPipeline
from geointel.providers.base import ModelRouter
from geointel.providers.offline import OfflineModel


@pytest.mark.skipif(not os.getenv("POSTGRES_TEST_URL"), reason="PostgreSQL service unavailable")
def test_postgres_repeated_persistence_and_forecast_immutability():
    engine = create_engine(os.environ["POSTGRES_TEST_URL"])
    model = OfflineModel()
    request = AnalysisRequest(
        location="Spain",
        question="Assess organized political violence in Spain for the next twelve months.",
        horizon_months=12,
    )
    with Session(engine, expire_on_commit=False) as session:
        pipeline = AnalysisPipeline(session, ModelRouter(model, model, model))
        first = pipeline.run(request)
        second = pipeline.run(request)
        assert first.id != second.id
        assert session.query(AnalysisRun).count() == 2
        assert session.query(Forecast).count() == 8
        forecast = session.scalar(select(Forecast).where(Forecast.analysis_run_id == first.id))
        forecast.rationale = "forbidden mutation"
        with pytest.raises(ValueError, match="immutable"):
            session.commit()


@pytest.mark.skipif(not os.getenv("POSTGRES_TEST_URL"), reason="PostgreSQL service unavailable")
def test_postgres_operational_event_and_predictive_signal_persistence():
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

    engine = create_engine(os.environ["POSTGRES_TEST_URL"])
    model = OfflineModel()
    request = AnalysisRequest(
        location="Spain",
        question="Assess organized political violence in Spain for the next twelve months.",
        horizon_months=12,
    )
    with Session(engine, expire_on_commit=False) as session:
        AnalysisPipeline(session, ModelRouter(model, model, model), [OperationalFixtures()]).run(
            request
        )
        assert (
            session.query(Event).filter_by(source_record_id="synthetic-postgres-event").count() == 1
        )
        assert (
            session.query(ForecastSignal)
            .filter_by(source_record_id="synthetic-postgres-signal", provider="CAST")
            .count()
            == 1
        )
