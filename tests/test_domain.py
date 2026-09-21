import pytest
from pydantic import ValidationError

from geointel.domain.models import AnalysisRun, Forecast, Location
from geointel.domain.schemas import (
    Confidence,
    ConflictType,
    ForecastOutput,
    RedTeamOutput,
    RiskAssessment,
    SynthesisOutput,
)


def assessment(kind):
    return RiskAssessment(conflict_type=kind, confidence=Confidence.LOW, rationale="test")


def test_probability_validation():
    with pytest.raises(ValidationError):
        RiskAssessment(
            conflict_type=ConflictType.INTERNAL,
            probability_low=0.8,
            probability_high=0.2,
            confidence=Confidence.LOW,
            rationale="test",
        )


def test_forecast_and_synthesis_require_taxonomy_exactly_once():
    incomplete = [assessment(ConflictType.INTERNAL)]
    with pytest.raises(ValidationError, match="each conflict type exactly once"):
        ForecastOutput(assessments=incomplete, overall_summary="incomplete")
    with pytest.raises(ValidationError, match="each conflict type exactly once"):
        SynthesisOutput(
            summary="incomplete",
            assessments=incomplete,
            incorporated_critiques=[],
            decision_support_notice="notice",
        )


def test_synthesis_must_incorporate_every_nonempty_red_team_finding():
    synthesis = SynthesisOutput(
        summary="summary",
        assessments=[assessment(kind) for kind in ConflictType],
        incorporated_critiques=[],
        decision_support_notice="notice",
    )
    red_team = RedTeamOutput(missing_evidence=["Missing source"])
    with pytest.raises(ValueError, match="Missing source"):
        synthesis.validate_red_team_incorporation(red_team)


def test_forecast_is_immutable(session):
    location = Location(name="Spain")
    session.add(location)
    session.flush()
    run = AnalysisRun(
        location_id=location.id,
        question="q",
        horizon_months=12,
        status="completed",
        pipeline_version="x",
        provider_config={},
        collection_metadata={},
    )
    session.add(run)
    session.flush()
    forecast = Forecast(
        analysis_run_id=run.id,
        conflict_type="internal_armed_conflict",
        question="q",
        horizon_months=12,
        version=1,
        confidence="low",
        rationale="x",
        evidence_for=[],
        evidence_against=[],
        unknowns=[],
        resolution_criteria=[],
        change_conditions=[],
    )
    session.add(forecast)
    session.commit()
    forecast.rationale = "changed"
    with pytest.raises(ValueError, match="immutable"):
        session.commit()
