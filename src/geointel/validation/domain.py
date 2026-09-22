from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from geointel.domain.schemas import ConflictType


class AssertionType(StrEnum):
    EXACT_CATEGORY_SET = "EXACT_CATEGORY_SET"
    FORECAST_IMMUTABILITY = "FORECAST_IMMUTABILITY"
    PROVENANCE_PRESENT = "PROVENANCE_PRESENT"
    SOURCE_SEPARATION = "SOURCE_SEPARATION"
    STRATEGIC_SEPARATION = "STRATEGIC_SEPARATION"
    MISSING_SOURCE_DISCLOSED = "MISSING_SOURCE_DISCLOSED"
    SOURCE_DISAGREEMENT_DISCLOSED = "SOURCE_DISAGREEMENT_DISCLOSED"
    NO_FAKE_PROBABILITY = "NO_FAKE_PROBABILITY"
    NO_SINGLE_EVENT_ESCALATION = "NO_SINGLE_EVENT_ESCALATION"
    NO_THEORY_OVERRIDE = "NO_THEORY_OVERRIDE"
    TEMPORAL_MISMATCH_DISCLOSED = "TEMPORAL_MISMATCH_DISCLOSED"
    GEOGRAPHIC_MISMATCH_DISCLOSED = "GEOGRAPHIC_MISMATCH_DISCLOSED"
    RED_TEAM_PRESENT = "RED_TEAM_PRESENT"
    RED_TEAM_CONSIDERS_BIAS = "RED_TEAM_CONSIDERS_BIAS"
    UNCERTAINTY_DISCLOSED = "UNCERTAINTY_DISCLOSED"
    FAILURE_NON_FATAL = "FAILURE_NON_FATAL"
    REPEATED_RUN_PRESERVES_HISTORY = "REPEATED_RUN_PRESERVES_HISTORY"
    REPRODUCIBLE_OFFLINE_RESULT = "REPRODUCIBLE_OFFLINE_RESULT"
    NO_CROSS_SOURCE_FUZZY_DEDUPE = "NO_CROSS_SOURCE_FUZZY_DEDUPE"
    CONTROL_FALSE_POSITIVE_GUARD = "CONTROL_FALSE_POSITIVE_GUARD"


class ResultStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    NOT_APPLICABLE = "not_applicable"


class ValidationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,39}$")
    country: str
    geography_id: str
    purpose: str
    scenario: str
    sources: dict[str, str]
    metadata: dict[str, str] = Field(
        default_factory=lambda: {"fixture_kind": "synthetic_behavioral_condition"}
    )
    version: str = "1"
    horizon_months: int = 12
    conflict_categories: tuple[ConflictType, ...] = tuple(ConflictType)
    assertions: tuple[AssertionType, ...] = tuple(AssertionType)

    @property
    def question(self) -> str:
        categories = "\n".join(f"- {item.value}" for item in self.conflict_categories)
        return (
            f"Analyze the risk of organized political violence in {self.country} over the next "
            f"12 months.\n\nSeparate:\n{categories}\n\nIdentify:\n- evidence for escalation\n"
            "- evidence against escalation\n- historical base rates\n- predictive signals\n"
            "- major unknowns\n- source disagreements\n- strategic interpretations\n"
            "- conditions that would materially change the assessment."
        )


class ValidationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suite_id: str
    version: str
    synthetic: bool
    notice: str
    cases: tuple[ValidationCase, ...]

    @model_validator(mode="after")
    def safe_suite(self):
        if not self.synthetic or "synthetic" not in self.notice.lower():
            raise ValueError("validation fixtures must be explicitly synthetic")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("case IDs must be unique")
        return self
