import os

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from geointel.domain.models import AnalysisRun, Forecast
from geointel.domain.schemas import AnalysisRequest
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
