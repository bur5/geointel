import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from geointel.connectors.base import DisabledConnector, EvidenceConnector
from geointel.domain.models import (
    AnalysisRun,
    Event,
    Evidence,
    Forecast,
    ForecastSignal,
    Location,
    Source,
)
from geointel.domain.schemas import (
    AnalysisRequest,
    AnalystOutput,
    ForecastOutput,
    NormalizedEvidence,
    NormalizedForecastSignal,
    NormalizedOperationalEvent,
    RedTeamOutput,
    SynthesisOutput,
)
from geointel.providers.base import ModelRouter

logger = logging.getLogger(__name__)
PIPELINE_VERSION = "0.0.3"


class AnalysisPipeline:
    def __init__(
        self,
        session: Session,
        router: ModelRouter,
        connectors: list[EvidenceConnector] | None = None,
    ):
        self.session, self.router, self.connectors = session, router, connectors or []

    def run(self, request: AnalysisRequest) -> AnalysisRun:
        try:
            return self._run(request)
        except Exception:
            self.session.rollback()
            raise

    def _run(self, request: AnalysisRequest) -> AnalysisRun:
        location = self.session.scalar(select(Location).where(Location.name == request.location))
        if not location:
            location = Location(name=request.location)
            self.session.add(location)
            self.session.flush()
        run = AnalysisRun(
            location_id=location.id,
            question=request.question,
            horizon_months=request.horizon_months,
            status="running",
            pipeline_version=PIPELINE_VERSION,
            provider_config=self.router.safe_config(),
            collection_metadata={},
        )
        self.session.add(run)
        self.session.flush()
        evidence: list[NormalizedEvidence] = []
        signals: list[NormalizedForecastSignal] = []
        events: list[NormalizedOperationalEvent] = []
        connector_errors = []
        outcomes = []
        for connector in self.connectors:
            connector_name = getattr(connector, "connector_name", type(connector).__name__)
            collected_at = datetime.now(UTC).isoformat()
            if isinstance(connector, DisabledConnector):
                outcomes.append(
                    {
                        "connector": connector_name,
                        "attempted": False,
                        "status": "disabled",
                        "succeeded": False,
                        "record_count": 0,
                        "failure_reason": None,
                        "collection_timestamp": collected_at,
                    }
                )
                continue
            try:
                records = connector.collect(request.location, request.horizon_months)
                if not all(
                    isinstance(
                        item,
                        (NormalizedEvidence, NormalizedForecastSignal, NormalizedOperationalEvent),
                    )
                    for item in records
                ):
                    raise TypeError("connector returned an unsupported normalized record type")
                records = self._deduplicate(records, self._record_key)
                evidence.extend(item for item in records if isinstance(item, NormalizedEvidence))
                signals.extend(
                    item for item in records if isinstance(item, NormalizedForecastSignal)
                )
                events.extend(
                    item for item in records if isinstance(item, NormalizedOperationalEvent)
                )
                outcomes.append(
                    {
                        "connector": connector_name,
                        "attempted": True,
                        "status": "succeeded",
                        "succeeded": True,
                        "record_count": len(records),
                        "failure_reason": None,
                        "collection_timestamp": collected_at,
                    }
                )
            except Exception as exc:
                safe_error = self._safe_error(exc)
                logger.warning(
                    "evidence_connector_failed",
                    extra={"connector": connector_name, "error": safe_error},
                )
                connector_errors.append({"connector": connector_name, "error": safe_error})
                outcomes.append(
                    {
                        "connector": connector_name,
                        "attempted": True,
                        "status": "failed",
                        "succeeded": False,
                        "record_count": 0,
                        "failure_reason": safe_error,
                        "collection_timestamp": collected_at,
                    }
                )
        evidence = self._deduplicate(evidence, self._record_key)
        signals = self._deduplicate(signals, self._record_key)
        events = self._deduplicate(events, self._record_key)
        for item in evidence:
            source = self.session.scalar(select(Source).where(Source.name == item.source_name))
            if not source:
                source = Source(
                    name=item.source_name,
                    source_type="structured_data",
                    reliability=item.reliability.value,
                )
                self.session.add(source)
                self.session.flush()
            self.session.add(
                Evidence(
                    analysis_run_id=run.id,
                    source_id=source.id,
                    location_id=location.id,
                    source_record_id=item.source_record_id,
                    title=item.title,
                    summary=item.summary,
                    url=item.url,
                    published_at=item.published_at,
                    event_date=item.event_date,
                    retrieved_at=item.retrieved_at,
                    reliability=item.reliability.value,
                    provenance=item.provenance,
                )
            )
        for item in events:
            source = self.session.scalar(select(Source).where(Source.name == item.provider))
            if not source:
                source = Source(
                    name=item.provider, source_type="operational_events", reliability="reported"
                )
                self.session.add(source)
                self.session.flush()
            self.session.add(
                Event(
                    analysis_run_id=run.id,
                    source_id=source.id,
                    source_record_id=item.source_record_id,
                    location_id=location.id,
                    event_type=item.event_type,
                    occurred_at=item.event_date,
                    description=item.notes or f"{item.event_type} reported in {item.country}",
                    confidence="reported",
                    provenance=item.model_dump(mode="json"),
                )
            )
        for item in signals:
            self.session.add(
                ForecastSignal(
                    analysis_run_id=run.id,
                    location_id=location.id,
                    provider=item.provider,
                    source_record_id=item.source_record_id,
                    model_name=item.model_name,
                    model_version=item.model_version,
                    geographic_unit=item.geographic_unit,
                    source_location=item.location,
                    issue_date=item.issue_date,
                    target_start=item.target_start,
                    target_end=item.target_end,
                    horizon_months=item.horizon_months,
                    target_variable=item.target_variable,
                    prediction=item.prediction,
                    unit=item.unit,
                    scale=item.scale,
                    retrieved_at=item.retrieved_at,
                    source_url=item.source_url,
                    alignment_status=item.alignment_status,
                    alignment_notes=item.alignment_notes,
                    provenance=item.provenance,
                )
            )
        run.collection_metadata = {
            "connector_count": len(self.connectors),
            "evidence_count": len(evidence),
            "forecast_signal_count": len(signals),
            "recent_event_count": len(events),
            "connector_failures": connector_errors,
            "connector_outcomes": outcomes,
            "external_collection_succeeded": any(item["succeeded"] for item in outcomes),
            "collected_at": datetime.now(UTC).isoformat(),
        }
        payload = {
            "request": request.model_dump(),
            "observed_evidence": [x.model_dump(mode="json") for x in evidence],
            "historical_evidence": [x.model_dump(mode="json") for x in evidence],
            "recent_events": [x.model_dump(mode="json") for x in events],
            # Compatibility alias for structured providers implemented against v0.0.1.
            "evidence": [x.model_dump(mode="json") for x in evidence],
            "predictive_signals": [x.model_dump(mode="json") for x in signals],
            "source_disagreements": self._alignment_disagreements(signals, events),
            "collection_metadata": run.collection_metadata,
            "connector_errors": connector_errors,
        }
        analyst = self.router.for_role("reasoning").generate("analyst", payload, AnalystOutput)
        forecast = self.router.for_role("reasoning").generate(
            "forecaster", {**payload, "analysis": analyst.model_dump()}, ForecastOutput
        )
        red = self.router.for_role("reasoning").generate(
            "red_team",
            {**payload, "analysis": analyst.model_dump(), "forecast": forecast.model_dump()},
            RedTeamOutput,
        )
        synthesis = self.router.for_role("reasoning").generate(
            "meta_analyst",
            {
                **payload,
                "analysis": analyst.model_dump(),
                "forecast": forecast.model_dump(),
                "red_team": red.model_dump(),
            },
            SynthesisOutput,
        )
        synthesis.validate_red_team_incorporation(red)
        run.analyst_output = analyst.model_dump(mode="json")
        run.red_team_output = red.model_dump(mode="json")
        run.synthesis_output = synthesis.model_dump(mode="json")
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        for assessment in synthesis.assessments:
            self.session.add(
                Forecast(
                    analysis_run_id=run.id,
                    conflict_type=assessment.conflict_type.value,
                    question=request.question,
                    horizon_months=request.horizon_months,
                    version=1,
                    probability_low=assessment.probability_low,
                    probability_high=assessment.probability_high,
                    confidence=assessment.confidence.value,
                    rationale=assessment.rationale,
                    evidence_for=assessment.evidence_for,
                    evidence_against=assessment.evidence_against,
                    unknowns=assessment.unknowns,
                    resolution_criteria=assessment.resolution_criteria,
                    change_conditions=assessment.change_conditions,
                )
            )
        self.session.commit()
        self.session.refresh(run)
        return run

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = " ".join(str(exc).split())
        return message[:500] or type(exc).__name__

    @staticmethod
    def _alignment_disagreements(signals, events) -> list[str]:
        notes = [note for item in [*signals, *events] for note in item.alignment_notes]
        providers = {signal.provider for signal in signals}
        if {"VIEWS", "CAST"} <= providers:
            notes.append(
                "VIEWS/CAST comparison is unresolved: provider-native targets and scales are "
                "retained without ensemble weighting"
            )
        if events and signals:
            notes.append(
                "ACLED/model relationship is unresolved: event reports neither validate nor "
                "override predictive signals"
            )
        return notes

    @staticmethod
    def _deduplicate(records, key):
        unique = {}
        for record in records:
            unique.setdefault(key(record), record)
        return list(unique.values())

    @staticmethod
    def _record_key(record):
        if isinstance(record, NormalizedEvidence):
            # Records without provider identity are kept distinct rather than guessed equal.
            return ("evidence", record.source_name, record.source_record_id or id(record))
        return (type(record).__name__, record.provider, record.source_record_id)
