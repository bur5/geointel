import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from geointel import __version__
from geointel.api.dashboard import router as dashboard_router
from geointel.config import Settings, get_settings
from geointel.connectors.acled import ACLEDConnector
from geointel.connectors.base import DisabledConnector, EvidenceConnector
from geointel.connectors.cast import CASTConnector
from geointel.connectors.gdelt import GDELTConnector
from geointel.connectors.newsapi import NewsAPIConnector
from geointel.connectors.ucdp import UCDPConnector
from geointel.connectors.views import VIEWSConnector
from geointel.domain.database import get_session
from geointel.domain.models import AnalysisRun, Forecast
from geointel.domain.schemas import AnalysisRequest, AnalysisResponse, ForecastResponse
from geointel.pipeline.service import AnalysisPipeline
from geointel.providers.acled_auth import ACLEDOAuthClient
from geointel.providers.base import ModelRouter
from geointel.providers.offline import OfflineModel
from geointel.providers.registry import public_capabilities
from geointel.providers.runtime import HardenedTransport

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.getLogger(__name__).info("geointel_starting", extra={"version": __version__})
    yield


app = FastAPI(title="GEOINTEL", version=__version__, lifespan=lifespan)
app.include_router(dashboard_router)

# Serve this entry point when the dashboard must be isolated from legacy routes.
dashboard_app = FastAPI(title="GEOINTEL Dashboard", version="1", lifespan=lifespan)
dashboard_app.include_router(dashboard_router)

SessionDependency = Annotated[Session, Depends(get_session)]


def router() -> ModelRouter:
    model = OfflineModel()
    return ModelRouter(model, model, model)


def connectors(settings: Settings | None = None) -> list[EvidenceConnector]:
    settings = settings or get_settings()
    result: list[EvidenceConnector] = []
    acled_transport = HardenedTransport(
        timeout=min(settings.acled_timeout_seconds, settings.cast_timeout_seconds),
        retries=max(settings.acled_max_retries, settings.cast_max_retries),
        max_bytes=settings.provider_max_response_bytes,
    )
    oauth = (
        ACLEDOAuthClient(
            settings.acled_username or "",
            settings.acled_password or "",
            acled_transport,
            settings.acled_oauth_url,
        )
        if settings.acled_username and settings.acled_password
        else None
    )
    result.append(
        UCDPConnector(
            base_url=settings.ucdp_base_url,
            api_version=settings.ucdp_dataset_version or settings.ucdp_api_version,
            endpoint_path=settings.ucdp_endpoint_path,
            access_token=settings.ucdp_access_token,
            timeout=settings.ucdp_timeout,
            retries=settings.ucdp_retries,
            official_api=settings.ucdp_mode.casefold() == "official_api",
            max_pages=settings.provider_max_pages,
            max_records=settings.provider_max_records,
            max_bytes=settings.provider_max_response_bytes,
            dataset_role=settings.ucdp_dataset_role,
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
    result.append(
        ACLEDConnector(
            settings.acled_base_url,
            settings.acled_endpoint_path,
            settings.acled_timeout_seconds,
            settings.acled_max_retries,
            official_api=settings.acled_mode.casefold() == "official_api",
            oauth=oauth,
            transport=acled_transport,
            max_pages=settings.provider_max_pages,
            max_records=settings.provider_max_records,
        )
        if settings.acled_enabled
        else DisabledConnector("ACLED")
    )
    result.append(
        CASTConnector(
            settings.cast_base_url,
            settings.cast_endpoint_path,
            settings.cast_timeout_seconds,
            settings.cast_max_retries,
            official_api=settings.cast_mode.casefold() == "official_api",
            oauth=oauth,
            transport=acled_transport,
            max_pages=settings.provider_max_pages,
            max_records=settings.provider_max_records,
        )
        if settings.cast_enabled
        else DisabledConnector("CAST")
    )
    if settings.gdelt_enabled:
        result.append(
            GDELTConnector(
                settings.gdelt_base_url,
                settings.gdelt_timeout_seconds,
                settings.gdelt_max_retries,
                transport=HardenedTransport(
                    timeout=settings.gdelt_timeout_seconds,
                    retries=settings.gdelt_max_retries,
                    max_bytes=settings.provider_max_response_bytes,
                    allow_private=settings.provider_allow_private_networks,
                ),
                max_records=min(settings.provider_max_records, 250),
            )
        )
    if settings.newsapi_enabled:
        result.append(
            NewsAPIConnector(
                settings.newsapi_base_url,
                settings.newsapi_api_key or "",
                settings.newsapi_timeout_seconds,
                settings.newsapi_max_retries,
                transport=HardenedTransport(
                    timeout=settings.newsapi_timeout_seconds,
                    retries=settings.newsapi_max_retries,
                    max_bytes=settings.provider_max_response_bytes,
                    allow_private=settings.provider_allow_private_networks,
                ),
                max_pages=settings.newsapi_max_pages,
                max_records=settings.newsapi_max_records,
                request_budget=settings.newsapi_request_budget,
                page_size=settings.newsapi_page_size,
                window_days=settings.newsapi_window_days,
                entitlement=settings.newsapi_entitlement,
            )
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
        strategic_context=[
            item.output | {"status": item.status} for item in run.strategic_analyses
        ],
        forecast_ids=[forecast.id for forecast in run.forecasts],
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/providers")
def provider_capabilities() -> list[dict]:
    """Operational metadata only; configuration secrets are never represented."""
    return public_capabilities(get_settings())


@app.post("/analysis", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
def create_analysis(body: AnalysisRequest, session: SessionDependency) -> AnalysisResponse:
    return present(AnalysisPipeline(session, router(), connectors()).run(body))


@app.get("/analysis/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: UUID, session: SessionDependency) -> AnalysisResponse:
    run = session.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.id == analysis_id)
        .options(
            selectinload(AnalysisRun.location),
            selectinload(AnalysisRun.forecasts),
            selectinload(AnalysisRun.strategic_analyses),
        )
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
