import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from geointel.connectors.base import EvidenceConnector
from geointel.domain.models import AnalysisRun, Evidence, Forecast, Location, Source
from geointel.domain.schemas import (AnalysisRequest, AnalystOutput, ForecastOutput,
 NormalizedEvidence, RedTeamOutput, SynthesisOutput)
from geointel.providers.base import ModelRouter
logger = logging.getLogger(__name__)
PIPELINE_VERSION = "0.0.1"
class AnalysisPipeline:
    def __init__(self, session: Session, router: ModelRouter, connectors: list[EvidenceConnector] | None = None):
        self.session, self.router, self.connectors = session, router, connectors or []
    def run(self, request: AnalysisRequest) -> AnalysisRun:
        location = self.session.scalar(select(Location).where(Location.name == request.location))
        if not location:
            location = Location(name=request.location); self.session.add(location); self.session.flush()
        run = AnalysisRun(location_id=location.id, question=request.question,
            horizon_months=request.horizon_months, status="running", pipeline_version=PIPELINE_VERSION,
            provider_config=self.router.safe_config())
        self.session.add(run); self.session.flush()
        normalized: list[NormalizedEvidence] = []
        connector_errors=[]
        for connector in self.connectors:
            try: normalized.extend(connector.collect(request.location))
            except Exception as exc:
                logger.warning("evidence_connector_failed", extra={"connector":type(connector).__name__, "error":str(exc)})
                connector_errors.append({"connector":type(connector).__name__, "error":str(exc)})
        for item in normalized:
            source = self.session.scalar(select(Source).where(Source.name == item.source_name))
            if not source:
                source=Source(name=item.source_name, source_type="structured_data", reliability=item.reliability.value)
                self.session.add(source); self.session.flush()
            self.session.add(Evidence(analysis_run_id=run.id, source_id=source.id, location_id=location.id,
                source_record_id=item.source_record_id, title=item.title, summary=item.summary, url=item.url,
                published_at=item.published_at, event_date=item.event_date, retrieved_at=item.retrieved_at,
                reliability=item.reliability.value, provenance=item.provenance))
        payload={"request":request.model_dump(), "evidence":[x.model_dump(mode="json") for x in normalized], "connector_errors":connector_errors}
        analyst=self.router.for_role("reasoning").generate("analyst", payload, AnalystOutput)
        forecast=self.router.for_role("reasoning").generate("forecaster", {**payload,"analysis":analyst.model_dump()}, ForecastOutput)
        red=self.router.for_role("reasoning").generate("red_team", {**payload,"analysis":analyst.model_dump(),"forecast":forecast.model_dump()}, RedTeamOutput)
        synthesis=self.router.for_role("reasoning").generate("meta_analyst", {**payload,"analysis":analyst.model_dump(),"forecast":forecast.model_dump(),"red_team":red.model_dump()}, SynthesisOutput)
        run.analyst_output=analyst.model_dump(mode="json"); run.red_team_output=red.model_dump(mode="json")
        run.synthesis_output=synthesis.model_dump(mode="json"); run.status="completed"; run.completed_at=datetime.now(timezone.utc)
        for assessment in synthesis.assessments:
            self.session.add(Forecast(analysis_run_id=run.id, conflict_type=assessment.conflict_type.value,
                question=request.question, horizon_months=request.horizon_months, version=1,
                probability_low=assessment.probability_low, probability_high=assessment.probability_high,
                confidence=assessment.confidence.value, rationale=assessment.rationale,
                evidence_for=assessment.evidence_for, evidence_against=assessment.evidence_against,
                unknowns=assessment.unknowns, resolution_criteria=assessment.resolution_criteria,
                change_conditions=assessment.change_conditions))
        self.session.commit(); self.session.refresh(run)
        return run
