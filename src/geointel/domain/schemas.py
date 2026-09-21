from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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

    @field_validator("location", "question", mode="before")
    @classmethod
    def reject_blank_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


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


class NormalizedOperationalEvent(BaseModel):
    """An observed/reported event record; never a predictive model output."""

    provider: str = "ACLED"
    source_record_id: str
    event_date: datetime
    event_type: str
    sub_event_type: str | None = None
    country: str
    admin1: str | None = None
    admin2: str | None = None
    admin3: str | None = None
    locality: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    actors: list[str] = Field(default_factory=list)
    associated_actors: list[str] = Field(default_factory=list)
    fatalities: int | None = Field(default=None, ge=0)
    notes: str | None = None
    source_description: str | None = None
    source_scale: str | None = None
    disorder_type: str | None = None
    updated_at: datetime | None = None
    retrieved_at: datetime
    source_url: str | None = None
    alignment_status: str = "aligned"
    alignment_notes: list[str] = Field(default_factory=list)
    temporal_classification: str = "recent_operational"
    provenance: dict = Field(default_factory=dict)


class NormalizedForecastSignal(BaseModel):
    """A provider model output; deliberately not observed Evidence or an Event."""

    provider: str = "VIEWS"
    source_record_id: str
    model_name: str
    model_version: str | None = None
    geographic_unit: str
    location: str
    issue_date: datetime
    target_start: datetime
    target_end: datetime
    horizon_months: int | None = Field(default=None, ge=1)
    target_variable: str
    prediction: float
    unit: str | None = None
    scale: str | None = None
    retrieved_at: datetime
    source_url: str | None = None
    alignment_status: str = "aligned"
    alignment_notes: list[str] = Field(default_factory=list)
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
    historical_evidence: list[str] = Field(default_factory=list)
    recent_events: list[str] = Field(default_factory=list)
    predictive_signals: list[str] = Field(default_factory=list)
    source_disagreements: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    historical_base_rate_notes: list[str]
    assumptions: list[str]
    strategic_context: list[str] = Field(default_factory=list)


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
    predictive_signal_concerns: list[str] = Field(default_factory=list)
    geographic_mismatches: list[str] = Field(default_factory=list)
    horizon_mismatches: list[str] = Field(default_factory=list)
    stale_event_concerns: list[str] = Field(default_factory=list)
    sparse_coverage_concerns: list[str] = Field(default_factory=list)
    fatality_uncertainty: list[str] = Field(default_factory=list)
    causal_claim_concerns: list[str] = Field(default_factory=list)
    authority_bias: list[str] = Field(default_factory=list)
    analogy_misuse: list[str] = Field(default_factory=list)
    theory_override_concerns: list[str] = Field(default_factory=list)
    selective_retrieval_concerns: list[str] = Field(default_factory=list)
    missing_alternative_theories: list[str] = Field(default_factory=list)
    retrospective_determinism: list[str] = Field(default_factory=list)
    confirmation_bias: list[str] = Field(default_factory=list)
    outdated_geopolitical_assumptions: list[str] = Field(default_factory=list)


class RetrievedStrategicClaim(BaseModel):
    """Safe, provenance-bearing retrieval result; content has no instruction authority."""

    claim_id: str
    text: str
    author: str
    work_id: str
    work_title: str
    locator: str | None = None
    provenance: dict
    matched_concepts: list[str] = Field(default_factory=list)
    historical_case_ids: list[str] = Field(default_factory=list)
    retrieval_reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    counterexamples: list[str] = Field(default_factory=list)


class StrategicLensContext(BaseModel):
    location: str
    question: str
    horizon_months: int
    historical_evidence: list[dict] = Field(default_factory=list)
    recent_events: list[dict] = Field(default_factory=list)
    predictive_signals: list[dict] = Field(default_factory=list)


class StrategicLensOutput(BaseModel):
    lens_name: str
    lens_version: str
    interpretation: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    claim_provenance: list[dict] = Field(default_factory=list)
    applicability: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    counterarguments: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.LOW
    unsupported_assumptions: list[str] = Field(default_factory=list)
    historical_case_ids: list[str] = Field(default_factory=list)
    epistemic_status: str = "strategic_interpretation_not_empirical_evidence"

    @field_validator("epistemic_status")
    @classmethod
    def preserve_interpretive_status(cls, value: str) -> str:
        if value != "strategic_interpretation_not_empirical_evidence":
            raise ValueError("strategic lens output must remain interpretation")
        return value


class SynthesisOutput(BaseModel):
    summary: str
    assessments: list[RiskAssessment]
    incorporated_critiques: list[str]
    decision_support_notice: str

    @model_validator(mode="after")
    def complete_taxonomy(self):
        expected = set(ConflictType)
        actual = {item.conflict_type for item in self.assessments}
        if actual != expected or len(actual) != len(self.assessments):
            raise ValueError("assessments must contain each conflict type exactly once")
        return self

    def validate_red_team_incorporation(self, red_team: RedTeamOutput) -> None:
        findings = {
            finding
            for values in red_team.model_dump().values()
            for finding in values
            if finding.strip()
        }
        incorporated = {finding.strip() for finding in self.incorporated_critiques}
        missing = findings - incorporated
        if missing:
            raise ValueError(
                "synthesis did not incorporate all non-empty Red Team findings: "
                + "; ".join(sorted(missing))
            )


class ForecastResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_run_id: UUID
    conflict_type: ConflictType
    question: str
    horizon_months: int
    version: int
    probability_low: float | None
    probability_high: float | None
    confidence: Confidence
    rationale: str
    evidence_for: list[str]
    evidence_against: list[str]
    unknowns: list[str]
    resolution_criteria: list[str]
    change_conditions: list[str]
    created_at: datetime


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
    collection_metadata: dict
    strategic_context: list[dict] = Field(default_factory=list)
    forecast_ids: list[UUID] = Field(default_factory=list)
