import pytest
from pydantic import ValidationError
from geointel.domain.models import Forecast
from geointel.domain.schemas import Confidence, ConflictType, RiskAssessment
def test_probability_validation():
    with pytest.raises(ValidationError):
        RiskAssessment(conflict_type=ConflictType.INTERNAL,probability_low=.8,probability_high=.2,
          confidence=Confidence.LOW,rationale="test")
def test_forecast_is_immutable(session):
    from geointel.domain.models import AnalysisRun,Location
    loc=Location(name="Spain");session.add(loc);session.flush()
    run=AnalysisRun(location_id=loc.id,question="q",horizon_months=12,status="completed",pipeline_version="x",provider_config={});session.add(run);session.flush()
    f=Forecast(analysis_run_id=run.id,conflict_type="internal",question="q",horizon_months=12,version=1,confidence="low",rationale="x",evidence_for=[],evidence_against=[],unknowns=[],resolution_criteria=[],change_conditions=[])
    session.add(f);session.commit();f.rationale="changed"
    with pytest.raises(ValueError,match="immutable"): session.commit()
