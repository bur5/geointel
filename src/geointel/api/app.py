import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from geointel import __version__
from geointel.config import get_settings
from geointel.connectors.base import DisabledConnector, EvidenceConnector
from geointel.connectors.ucdp import UCDPConnector
from geointel.connectors.views import VIEWSConnector
from geointel.domain.database import get_session
from geointel.domain.models import AnalysisRun, Forecast
from geointel.domain.schemas import AnalysisRequest, AnalysisResponse, ForecastResponse
from geointel.pipeline.service import AnalysisPipeline
from geointel.providers.base import ModelRouter
from geointel.providers.offline import OfflineModel

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.getLogger(__name__).info("geointel_starting", extra={"version": __version__})
    yield


app = FastAPI(title="GEOINTEL", version=__version__, lifespan=lifespan)
SessionDependency = Annotated[Session, Depends(get_session)]


def router() -> ModelRouter:
    model = OfflineModel()
    return ModelRouter(model, model, model)


def connectors() -> list[EvidenceConnector]:
    settings = get_settings()
    result: list[EvidenceConnector] = []
    result.append(
        UCDPConnector(
            base_url=settings.ucdp_base_url,
            api_version=settings.ucdp_api_version,
            endpoint_path=settings.ucdp_endpoint_path,
            access_token=settings.ucdp_access_token,
            timeout=settings.ucdp_timeout,
            retries=settings.ucdp_retries,
        )
        if settings.ucdp_enabled
        else DisabledConnector("UCDP")
    )
    result.append(
        VIEWSConnector(
            base_url=settings.views_base_url,
            endpoint_path=settings.views_endpoint_path,
            timeout=settings.views_timeout_seconds,
            retries=settings.views_max_retries,
        )
        if settings.views_enabled
        else DisabledConnector("VIEWS")
    )
    return result


def present(run: AnalysisRun) -> AnalysisResponse:
    return AnalysisResponse(
        id=run.id,
        status=run.status,
        location=run.location.name,
        question=run.question,
        horizon_months=run.horizon_months,
        pipeline_version=run.pipeline_version,
        created_at=run.created_at,
        completed_at=run.completed_at,
        analyst_output=run.analyst_output,
        red_team_output=run.red_team_output,
        synthesis_output=run.synthesis_output,
        collection_metadata=run.collection_metadata,
        forecast_ids=[forecast.id for forecast in run.forecasts],
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/analysis", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
def create_analysis(body: AnalysisRequest, session: SessionDependency) -> AnalysisResponse:
    return present(AnalysisPipeline(session, router(), connectors()).run(body))


@app.get("/analysis/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: UUID, session: SessionDependency) -> AnalysisResponse:
    run = session.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.id == analysis_id)
        .options(selectinload(AnalysisRun.location), selectinload(AnalysisRun.forecasts))
    )
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return present(run)


@app.get("/forecasts", response_model=list[ForecastResponse])
def list_forecasts(session: SessionDependency) -> list[Forecast]:
    return list(session.scalars(select(Forecast).order_by(Forecast.created_at.desc())).all())


@app.get("/forecasts/{forecast_id}", response_model=ForecastResponse)
def get_forecast(forecast_id: UUID, session: SessionDependency) -> Forecast:
    forecast = session.get(Forecast, forecast_id)
    if not forecast:
        raise HTTPException(status_code=404, detail="Forecast not found")
    return forecast
