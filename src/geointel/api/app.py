import logging
from contextlib import asynccontextmanager
from uuid import UUID
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from geointel import __version__
from geointel.config import get_settings
from geointel.domain.database import get_session
from geointel.domain.models import AnalysisRun, Forecast
from geointel.domain.schemas import AnalysisRequest, AnalysisResponse
from geointel.pipeline.service import AnalysisPipeline
from geointel.providers.base import ModelRouter
from geointel.providers.offline import OfflineModel
logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger(__name__).info("geointel_starting", extra={"version":__version__})
    yield
app = FastAPI(title="GEOINTEL", version=__version__, lifespan=lifespan)

def router() -> ModelRouter:
    # Only the safe offline provider ships in v0.0.1; external providers implement StructuredModel.
    model=OfflineModel(); return ModelRouter(model, model, model)
def present(run: AnalysisRun) -> AnalysisResponse:
    return AnalysisResponse(id=run.id, status=run.status, location=run.location.name,
        question=run.question, horizon_months=run.horizon_months, pipeline_version=run.pipeline_version,
        created_at=run.created_at, completed_at=run.completed_at, analyst_output=run.analyst_output,
        red_team_output=run.red_team_output, synthesis_output=run.synthesis_output,
        forecast_ids=[f.id for f in run.forecasts])
@app.get("/health")
def health(): return {"status":"ok", "version":__version__}
@app.post("/analysis", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
def create_analysis(body: AnalysisRequest, session: Session=Depends(get_session)):
    return present(AnalysisPipeline(session, router()).run(body))
@app.get("/analysis/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: UUID, session: Session=Depends(get_session)):
    run=session.scalar(select(AnalysisRun).where(AnalysisRun.id==analysis_id).options(
        selectinload(AnalysisRun.location), selectinload(AnalysisRun.forecasts)))
    if not run: raise HTTPException(404, "Analysis run not found")
    return present(run)
@app.get("/forecasts")
def list_forecasts(session: Session=Depends(get_session)):
    return [forecast_dict(x) for x in session.scalars(select(Forecast).order_by(Forecast.created_at.desc())).all()]
@app.get("/forecasts/{forecast_id}")
def get_forecast(forecast_id: UUID, session: Session=Depends(get_session)):
    forecast=session.get(Forecast, forecast_id)
    if not forecast: raise HTTPException(404, "Forecast not found")
    return forecast_dict(forecast)
def forecast_dict(f: Forecast) -> dict:
    return {"id":f.id,"analysis_run_id":f.analysis_run_id,"conflict_type":f.conflict_type,
        "question":f.question,"horizon_months":f.horizon_months,"version":f.version,
        "probability_low":f.probability_low,"probability_high":f.probability_high,
        "confidence":f.confidence,"rationale":f.rationale,"evidence_for":f.evidence_for,
        "evidence_against":f.evidence_against,"unknowns":f.unknowns,
        "resolution_criteria":f.resolution_criteria,"change_conditions":f.change_conditions,"created_at":f.created_at}
