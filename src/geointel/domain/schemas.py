from datetime import datetime
from enum import StrEnum
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

class ConflictType(StrEnum):
    INTERSTATE = "interstate_armed_conflict"
    INTERNAL = "internal_armed_conflict"
    ONE_SIDED = "one_sided_violence"
    POLITICAL = "major_political_violence"

class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class AnalysisRequest(BaseModel):
    location: str = Field(min_length=2, max_length=120)
    question: str = Field(min_length=20, max_length=2000)
    horizon_months: int = Field(ge=1, le=120)

class NormalizedEvidence(BaseModel):
    source_name: str
    source_record_id: str | None = None
    title: str
    summary: str
    url: str | None = None
    published_at: datetime | None = None
    event_date: datetime | None = None
    retrieved_at: datetime
    geographic_scope: str
    reliability: Confidence = Confidence.MEDIUM
    provenance: dict = Field(default_factory=dict)

class RiskAssessment(BaseModel):
    conflict_type: ConflictType
    probability_low: float | None = Field(default=None, ge=0, le=1)
    probability_high: float | None = Field(default=None, ge=0, le=1)
    confidence: Confidence
    rationale: str
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    resolution_criteria: list[str] = Field(default_factory=list)
    change_conditions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered_range(self):
        if (self.probability_low is None) != (self.probability_high is None):
            raise ValueError("probability range requires both bounds")
        if self.probability_low is not None and self.probability_low > self.probability_high:
            raise ValueError("probability_low must not exceed probability_high")
        return self

class AnalystOutput(BaseModel):
    observed_evidence: list[str]
    historical_base_rate_notes: list[str]
    assumptions: list[str]

class ForecastOutput(BaseModel):
    assessments: list[RiskAssessment]
    overall_summary: str

    @model_validator(mode="after")
    def complete_taxonomy(self):
        expected = set(ConflictType)
        actual = {x.conflict_type for x in self.assessments}
        if actual != expected or len(actual) != len(self.assessments):
            raise ValueError("assessments must contain each conflict type exactly once")
        return self

class RedTeamOutput(BaseModel):
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    base_rate_concerns: list[str] = Field(default_factory=list)
    sensationalism_risks: list[str] = Field(default_factory=list)
    duplicated_evidence: list[str] = Field(default_factory=list)
    unjustified_precision: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    false_positive_risks: list[str] = Field(default_factory=list)

class SynthesisOutput(BaseModel):
    summary: str
    assessments: list[RiskAssessment]
    incorporated_critiques: list[str]
    decision_support_notice: str

class AnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    location: str
    question: str
    horizon_months: int
    pipeline_version: str
    created_at: datetime
    completed_at: datetime | None
    analyst_output: dict | None
    red_team_output: dict | None
    synthesis_output: dict | None
    forecast_ids: list[UUID] = Field(default_factory=list)
