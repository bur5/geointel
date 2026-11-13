"""Strict, bounded data contracts. Text is data, never executable instructions."""

from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
Timestamp = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")]
SourceRef = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=300,
        pattern=r"^(urn:[A-Za-z0-9._:/-]+|https://github\.com/bur5/geointel/[A-Za-z0-9._/#-]+)$",
    ),
]
Risk = Literal["R0", "R1", "R2", "R3"]
Mode = Literal["read_only", "isolated_proposal", "reserved_action"]
Category = Literal[
    "security_defect",
    "integrity_defect",
    "ci_reproducibility",
    "infrastructure_blocker",
    "documentation",
    "product_improvement",
]
Effect = Literal[
    "assessment",
    "documentation",
    "maintenance",
    "forecast_model",
    "evidence_processing",
    "architecture",
    "persistence",
    "security_implementation",
    "protected_policy",
    "authority",
    "workflow_gate",
    "reviewer_identity",
    "permissions",
    "secrets",
    "security_boundary",
    "scientific_integrity",
    "deletion",
    "spending",
    "deployment",
    "public_release",
    "external_integration",
]
Dependency = Annotated[
    str, StringConstraints(pattern=r"^(pr:(24|25|26)|task:[a-z][a-z0-9_-]{0,63})$")
]
RepoPath = Annotated[
    str, StringConstraints(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_./-]+$")
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)

    @field_validator("*", mode="before")
    @classmethod
    def inert_text(cls, value):
        if isinstance(value, str) and any(ord(char) < 32 for char in value):
            raise ValueError("control characters are forbidden")
        return value


class Refs(StrictModel):
    head_sha: Sha
    base_sha: Sha
    base_branch: Literal["main"]


class Evidence(Refs):
    id: Key
    source_id: Key
    source_ref: SourceRef
    observed_at: Timestamp
    topic: Literal["repository_refs", "work_item", "ci", "review", "other"]
    subject: Key
    value: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    status: Literal["operator_attested", "observed", "unknown", "conflicting"]


class Scope(StrictModel):
    category: Category
    mode: Mode
    paths: list[RepoPath] = Field(min_length=1, max_length=20)
    effects: list[Effect] = Field(min_length=1, max_length=20)

    @field_validator("paths")
    @classmethod
    def repository_paths(cls, paths):
        for path in paths:
            parsed = PurePosixPath(path)
            if (
                not parsed.parts
                or parsed.is_absolute()
                or ".." in parsed.parts
                or str(parsed) != path
                or "\\" in path
                or ":" in path
                or any(c in path for c in "*?[]")
                or any(part.startswith(".") for part in parsed.parts if part != ".github")
            ):
                raise ValueError("literal repository paths only; no hidden credential paths")
        return paths

    @field_validator("paths", "effects")
    @classmethod
    def unique_scope(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("duplicate scope")
        return values


class Assessment(Scope):
    task_key: Key
    risk_floor: Risk
    classification: Literal["clear", "uncertain", "disputed"]
    scientific_boundaries: Literal["preserved", "unknown", "violation"]
    evidence_ids: list[Key] = Field(min_length=1, max_length=20)


class PullRequest(StrictModel):
    number: Literal[24, 25, 26]
    head_sha: Sha
    state: Literal["open"]
    draft: bool
    resolution: Literal["unresolved"]


class Snapshot(Refs):
    @field_validator("private", mode="before")
    @classmethod
    def strictly_private(cls, value):
        if value is not True:
            raise ValueError("private must be the JSON boolean true")
        return value

    repository: Literal["bur5/geointel"]
    private: Literal[True]
    source_id: Key
    source_ref: SourceRef
    provenance_status: Literal["operator_attested", "unverifiable"]
    captured_at: Timestamp
    evidence: list[Evidence] = Field(min_length=1, max_length=100)
    assessments: list[Assessment] = Field(max_length=32)
    open_prs: list[PullRequest] = Field(min_length=3, max_length=3)


class Candidate(Scope, Refs):
    key: Key
    title: Text
    description: Text
    declared_risk: Risk
    dependencies: list[Dependency] = Field(max_length=20)
    evidence_ids: list[Key] = Field(min_length=1, max_length=20)
    effort: int = Field(ge=1, le=5)


class PlanningInput(StrictModel):
    schema_version: Literal["geointel-manager-input-v1"]
    evaluation_at: Timestamp
    snapshot: Snapshot
    candidates: list[Candidate] = Field(max_length=32)

    @field_validator("evaluation_at")
    @classmethod
    def valid_clock(cls, value):
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return value


class AuditEntry(StrictModel):
    sequence: int
    rule: str
    subject: str
    result: str
    evidence_ids: list[str]


class RankedItem(StrictModel):
    rank: int
    key: str
    task_id: str
    risk: Risk
    state: Literal["ELIGIBLE_FOR_CONTRACT", "BLOCKED"]
    rationale: list[str]
    blockers: list[str]
    dependencies: list[str]
    category_priority: int
    effort: int


class Contract(StrictModel):
    task_id: str
    state: Literal["PROPOSED_NOT_AUTHORIZED"]
    task_key: str
    snapshot_sha256: str
    head_sha: Sha
    base_sha: Sha
    risk: Risk
    objective: str
    mode: Mode
    paths: list[str]
    dependencies: list[str]
    evidence_ids: list[str]
    acceptance_criteria: list[str]
    verification_plan: list[str]
    stop_conditions: list[str]
    authority_boundaries: list[str]
    max_corrective_iterations: Literal[2]
    implementation_requires_new_authorized_task: Literal[True]


class Plan(StrictModel):
    schema_version: Literal["geointel-manager-plan-v1"]
    engine_version: Literal["0.1"]
    state: Literal["CONTRACT_PROPOSED", "BLOCKED"]
    advisory: Literal[True]
    action_authorized: Literal[False]
    independent_reviewer: Literal[False]
    plan_id: str | None
    snapshot_sha256: str | None
    input_sha256: str | None
    evaluation_at: str | None
    snapshot_provenance: dict[str, str] | None
    refs: Refs | None
    target_governance: str
    unresolved_prs: list[int]
    blocking_reasons: list[str]
    authority_boundaries: list[str]
    prioritized_items: list[RankedItem]
    selected_contract: Contract | None
    audit: list[AuditEntry]
