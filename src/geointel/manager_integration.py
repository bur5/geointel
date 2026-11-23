"""Offline bridge from the pinned collector to advisory Manager data."""

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

COLLECTOR_REVISION = "3ada4193588a4c6bcb21b23dd9330831cefd2d86"
REPOSITORY = "bur5/geointel"
PREFIX = f"/repos/{REPOSITORY}"
PR_DETAIL = re.compile(rf"{re.escape(PREFIX)}/pulls/([1-9][0-9]*)")
JOBS = {"test (3.11)", "test (3.12)", "postgres-integration"}
MAX_AGE = timedelta(minutes=5)

Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Stamp = Annotated[
    str, StringConstraints(pattern=r"^[0-9]{4}(-[0-9]{2}){2}T[0-9]{2}(:[0-9]{2}){2}Z$")
]
Name = Annotated[str, StringConstraints(pattern=r"^[^\x00-\x20\x7f]+$", max_length=200)]
Positive = Annotated[int, Field(gt=0)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    @model_validator(mode="before")
    @classmethod
    def strict_boolean_literals(cls, value: object) -> object:
        if isinstance(value, dict):
            for name, field in cls.model_fields.items():
                if field.annotation in (Literal[True], Literal[False]) and name in value:
                    if type(value[name]) is not bool:
                        raise ValueError("boolean literal required")
        return value


class Repository(Record):
    id: Literal[1375475901]
    full_name: Literal["bur5/geointel"]
    private: Literal[True]
    default_branch: Name
    default_sha: Sha


class Workflow(Record):
    id: Positive
    path: Literal[".github/workflows/ci.yml"]
    state: Literal["active"]


class Source(Record):
    sequence: Positive
    method: Literal["GET"]
    endpoint: Annotated[str, StringConstraints(pattern=r"^/repos/bur5/geointel(?:/[^?# ]+)?$")]
    page: Positive | None
    query: dict[str, str | int]
    status_code: Literal[200]
    request_id: Name
    server_date: Stamp
    received_at: Stamp
    response_sha256: Digest


class Job(Record):
    id: Positive
    check_run_id: Positive
    app_id: Literal[15368]
    app_slug: Literal["github-actions"]
    name: Literal["test (3.11)", "test (3.12)", "postgres-integration"]
    head_sha: Sha
    run_id: Positive
    attempt: Positive
    status: Literal["completed"]
    conclusion: Literal["success"]
    state: Literal["success"]
    started_at: Stamp
    completed_at: Stamp
    source_metadata_matched: Literal[True]
    test_execution_independently_verified: Literal[False]


class CI(Record):
    run_id: Positive
    attempt: Positive
    workflow_id: Positive
    path: Literal[".github/workflows/ci.yml"]
    head_sha: Sha
    reported_base_sha: Sha
    reported_base_branch: Name
    status: Literal["completed"]
    conclusion: Literal["success"]
    state: Literal["success"]
    created_at: Stamp
    updated_at: Stamp
    historical_checkout_verified: Literal[False]
    jobs: Annotated[list[Job], Field(min_length=3, max_length=3)]


class Review(Record):
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


class PullRequest(Record):
    number: Positive
    state: Literal["open"]
    draft: bool
    head_sha: Sha
    head_repository: Name
    base_branch: Name
    base_sha: Sha
    updated_at: Stamp
    ci: CI
    reviews: Annotated[list[Review], Field(max_length=300)]
    content_handling: Literal["prose_excluded_from_snapshot_and_authority"]


class Observation(Record):
    started_at: Stamp
    completed_at: Stamp
    repository: Repository
    ci_workflow: Workflow
    pull_requests: Annotated[list[PullRequest], Field(max_length=25)]
    sources: Annotated[list[Source], Field(min_length=1, max_length=200)]
    content_digest: Digest


class ManagerInput(Record):
    schema_version: Literal["geointel-manager-input-v0.3"]
    collector_revision: Literal["3ada4193588a4c6bcb21b23dd9330831cefd2d86"]
    observed_github: Observation
    revalidation: Observation
    untrusted_content: Literal["excluded"]
    recommendation_authority: Literal["advisory_only"]
    authenticated_owner_decision: None
    autonomous_merge_enabled: Literal[False]
    action_authorized: Literal[False]


class ContractError(ValueError):
    """Stable rejection reason for the caller."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractError(code)


def stamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def validate_pr(
    pr: PullRequest, workflow: Workflow, end: datetime, endpoints: Counter[str]
) -> None:
    ci = pr.ci
    require(
        (ci.workflow_id, ci.head_sha, ci.reported_base_branch, ci.reported_base_sha)
        == (workflow.id, pr.head_sha, pr.base_branch, pr.base_sha),
        "CI_BINDING_MISMATCH",
    )
    require(
        stamp(pr.updated_at) <= end and stamp(ci.created_at) <= stamp(ci.updated_at) <= end,
        "INVALID_METADATA_TIME",
    )
    require(
        {job.name for job in ci.jobs} == JOBS
        and len({job.id for job in ci.jobs}) == len({job.check_run_id for job in ci.jobs}) == 3,
        "INCOMPLETE_OR_CONFLICTING_JOBS",
    )
    required = {
        f"{PREFIX}/actions/runs/{ci.run_id}/attempts/{ci.attempt}/jobs",
    }
    for job in ci.jobs:
        require(
            (job.head_sha, job.run_id, job.attempt) == (pr.head_sha, ci.run_id, ci.attempt),
            "JOB_BINDING_MISMATCH",
        )
        require(stamp(job.started_at) <= stamp(job.completed_at) <= end, "INVALID_METADATA_TIME")
        required.add(f"{PREFIX}/check-runs/{job.check_run_id}")
    require(all(endpoints[path] >= 1 for path in required), "MISSING_PROVENANCE")
    repeated = (
        f"{PREFIX}/pulls/{pr.number}",
        f"{PREFIX}/pulls/{pr.number}/reviews",
        f"{PREFIX}/actions/runs/{ci.run_id}",
    )
    require(all(endpoints[path] >= 2 for path in repeated), "MISSING_RECHECK_PROVENANCE")
    require(len({review.id for review in pr.reviews}) == len(pr.reviews), "DUPLICATE_REVIEW")
    for review in pr.reviews:
        require(review.stale_head == (review.commit_id != pr.head_sha), "REVIEW_BINDING_MISMATCH")
        require(
            not review.stale_head and review.state != "PENDING" and review.submitted_at is not None,
            "STALE_OR_INCOMPLETE_REVIEW",
        )
        require(stamp(review.submitted_at) <= end, "INVALID_METADATA_TIME")


def _normalize(raw: dict, now: datetime) -> Observation:
    require(
        raw.get("schema_version") == "geointel-github-observations-v0.2"
        and raw.get("producer") == "geointel-github-collector/0.2"
        and raw.get("transport") == "https-github-rest",
        "UNSUPPORTED_COLLECTOR",
    )
    require(
        raw.get("state") == "OBSERVED"
        and raw.get("observations_complete") is True
        and raw.get("advisory") is True
        and raw.get("action_authorized") is False
        and raw.get("issues") == [],
        "INCOMPLETE_OBSERVATION",
    )
    envelope_fields = {
        "schema_version",
        "producer",
        "transport",
        "state",
        "observations_complete",
        "advisory",
        "action_authorized",
        "issues",
        "trust_boundary",
        "digest_role",
        "manager_v01",
    }
    require(
        raw.keys() == envelope_fields | Observation.model_fields.keys(),
        "INVALID_OBSERVATION",
    )
    require(
        raw["trust_boundary"] == "api_metadata_observation_not_independent_review_or_owner_approval"
        and raw["digest_role"] == "integrity_only_not_authenticated_authorization",
        "UNSUPPORTED_TRUST_BOUNDARY",
    )
    try:
        digest_body = {key: value for key, value in raw.items() if key != "content_digest"}
        encoded = json.dumps(digest_body, sort_keys=True, separators=(",", ":"), allow_nan=False)
        require(
            hashlib.sha256(encoded.encode()).hexdigest() == raw.get("content_digest"),
            "INTEGRITY_MISMATCH",
        )
        snapshot = Observation.model_validate({key: raw[key] for key in Observation.model_fields})
        start, end = stamp(snapshot.started_at), stamp(snapshot.completed_at)
        require(now - MAX_AGE <= start <= end <= now, "STALE_OR_FUTURE_OBSERVATION")
        require(end - start <= timedelta(seconds=120), "CAPTURE_WINDOW_EXCEEDED")
        endpoints = Counter(source.endpoint for source in snapshot.sources)
        run_heads = {
            source.query.get("head_sha")
            for source in snapshot.sources
            if source.endpoint == f"{PREFIX}/actions/workflows/{snapshot.ci_workflow.id}/runs"
            and source.page == 1
            and source.query.get("event") == "pull_request"
        }
        required_rechecks = [PREFIX, f"{PREFIX}/actions/workflows/ci.yml"]
        require(
            sum(
                source.endpoint == f"{PREFIX}/pulls"
                and source.page == 1
                and source.query.get("state") == "open"
                for source in snapshot.sources
            )
            >= 2,
            "MISSING_RECHECK_PROVENANCE",
        )
        for index, source in enumerate(snapshot.sources, start=1):
            require(
                source.sequence == index
                and start <= stamp(source.received_at) <= end
                and abs(stamp(source.received_at) - stamp(source.server_date)) <= MAX_AGE,
                "INVALID_PROVENANCE",
            )
        seen = set()
        bases = {snapshot.repository.default_branch: snapshot.repository.default_sha}
        for pr in snapshot.pull_requests:
            require(pr.number not in seen, "DUPLICATE_PR")
            seen.add(pr.number)
            require(bases.setdefault(pr.base_branch, pr.base_sha) == pr.base_sha, "BASE_CONFLICT")
            require(pr.head_sha in run_heads, "MISSING_CI_LOOKUP_PROVENANCE")
            validate_pr(pr, snapshot.ci_workflow, end, endpoints)
            pr.ci.jobs.sort(key=lambda job: job.id)
            pr.reviews.sort(key=lambda review: review.id)
        observed_numbers = {
            int(detail[1]) for path in endpoints if (detail := PR_DETAIL.fullmatch(path))
        }
        require(seen == observed_numbers, "INVENTORY_PROVENANCE_MISMATCH")
        required_rechecks.extend(f"{PREFIX}/branches/{quote(base, safe='')}" for base in bases)
        require(
            all(endpoints[path] >= 2 for path in required_rechecks),
            "MISSING_RECHECK_PROVENANCE",
        )
        snapshot.pull_requests.sort(key=lambda pr: pr.number)
    except ContractError:
        raise
    except (KeyError, TypeError, ValueError):
        raise ContractError("INVALID_OBSERVATION") from None
    return snapshot


def prepare_manager_input(
    read_observation: Callable[[], dict],
    *,
    collector_revision: str,
    clock: Callable[[], datetime],
) -> ManagerInput:
    """Call only with a locally pinned collector and a trusted UTC clock."""
    require(collector_revision == COLLECTOR_REVISION, "UNSUPPORTED_COLLECTOR_REVISION")
    try:
        first_raw = read_observation()
        first = _normalize(first_raw, clock())
        second_raw = read_observation()
        now = clock()
        second = _normalize(second_raw, now)
    except ContractError:
        raise
    except Exception:
        raise ContractError("OBSERVATION_UNAVAILABLE") from None
    require(
        now - MAX_AGE
        <= stamp(first.started_at)
        <= stamp(first.completed_at)
        < stamp(second.started_at),
        "STALE_OR_REPLAYED_OBSERVATION",
    )
    require(
        (first.repository, first.ci_workflow, first.pull_requests)
        == (second.repository, second.ci_workflow, second.pull_requests),
        "OBSERVATION_CHANGED",
    )
    return ManagerInput(
        schema_version="geointel-manager-input-v0.3",
        collector_revision=COLLECTOR_REVISION,
        observed_github=first,
        revalidation=second,
        untrusted_content="excluded",
        recommendation_authority="advisory_only",
        authenticated_owner_decision=None,
        autonomous_merge_enabled=False,
        action_authorized=False,
    )
