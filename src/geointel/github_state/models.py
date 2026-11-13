"""Allowlisted metadata only. Schema validity is not approval or independent review."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Name = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Positive = Annotated[int, Field(gt=0)]
Stamp = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")]
State = Literal["success", "failure", "pending", "skipped", "unknown"]


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="before")
    @classmethod
    def no_controls(cls, value, info):
        if isinstance(value, str) and any(ord(char) < 32 for char in value):
            raise ValueError("control characters")
        if isinstance(value, str) and info.field_name.endswith("_at"):
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return value


class Repository(Metadata):
    id: Positive
    full_name: Literal["bur5/geointel"]
    private: Literal[True]
    default_branch: Name
    default_sha: Sha


class Workflow(Metadata):
    id: Positive
    path: Literal[".github/workflows/ci.yml"]
    state: Literal["active"]


class Source(Metadata):
    sequence: Positive
    method: Literal["GET"]
    endpoint: Annotated[str, StringConstraints(min_length=1, max_length=1500)]
    page: int | None
    query: dict[str, str | int]
    status_code: int
    request_id: str | None
    server_date: str | None
    received_at: Stamp
    response_sha256: Digest | None


class Job(Metadata):
    id: Positive
    check_run_id: Positive
    app_id: Positive
    app_slug: Name
    name: Name
    head_sha: Sha
    run_id: Positive
    attempt: Positive
    status: Name
    conclusion: Name | None
    state: State
    started_at: Stamp | None
    completed_at: Stamp | None
    source_metadata_matched: bool
    test_execution_independently_verified: Literal[False]


class CI(Metadata):
    run_id: Positive
    attempt: Positive
    workflow_id: Positive
    path: Name
    head_sha: Sha
    reported_base_sha: Sha
    reported_base_branch: Name
    status: Name
    conclusion: Name | None
    state: State
    created_at: Stamp
    updated_at: Stamp
    historical_checkout_verified: Literal[False]
    jobs: list[Job] = Field(max_length=300)


class Review(Metadata):
    id: Positive
    user_id: Positive
    login: Name
    user_type: Literal["User", "Bot", "Organization", "Mannequin"]
    state: Literal["APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"]
    commit_id: Sha | None
    submitted_at: Stamp | None
    stale_head: bool
    historical_base_verified: Literal[False]
    independence_verified: Literal[False]
    owner_authorization_verified: Literal[False]


class PullRequest(Metadata):
    number: Positive
    state: Literal["open"]
    draft: bool
    head_sha: Sha
    head_repository: Name
    base_branch: Name
    base_sha: Sha
    updated_at: Stamp
    ci: CI | None
    reviews: list[Review] = Field(max_length=300)
    content_handling: Literal["prose_excluded_from_snapshot_and_authority"]


class Compatibility(Metadata):
    target: Literal["pr27:6b7108de3865692381d9003b9231cdfa4eb92da8"]
    state: Literal["BLOCKED", "STRUCTURAL_FIXTURE_COMPATIBLE_ONLY"]
    reasons: list[str]
    payload: dict | None
    owner_authorization_verified: Literal[False]


class Snapshot(Metadata):
    schema_version: Literal["geointel-github-observations-v0.2"]
    state: Literal["OBSERVED", "BLOCKED"]
    observations_complete: bool
    advisory: Literal[True]
    action_authorized: Literal[False]
    producer: Literal["geointel-github-collector/0.2"]
    transport: Literal["https-github-rest", "mock"]
    started_at: Stamp
    completed_at: Stamp
    repository: Repository | None
    ci_workflow: Workflow | None
    pull_requests: list[PullRequest] = Field(max_length=25)
    sources: list[Source] = Field(max_length=200)
    issues: list[str]
    trust_boundary: Literal["api_metadata_observation_not_independent_review_or_owner_approval"]
    content_digest: Digest | None
    digest_role: Literal["integrity_only_not_authenticated_authorization"]
    manager_v01: Compatibility
