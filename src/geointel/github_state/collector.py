"""Read-only observation orchestration. No PR prose, approvals, dispatch or gate activation."""

from datetime import datetime
from urllib.parse import quote

from pydantic import ValidationError

from geointel.github_state.api import PREFIX, CollectionError, digest, stamp
from geointel.github_state.models import (
    CI,
    Compatibility,
    Job,
    PullRequest,
    Repository,
    Review,
    Snapshot,
    Workflow,
)

CI_JOBS = {"test (3.11)", "test (3.12)", "postgres-integration"}
TARGET = "pr27:6b7108de3865692381d9003b9231cdfa4eb92da8"


def need(condition, code):
    if not condition:
        raise CollectionError(code)


def state(status, conclusion):
    if (
        status in {"queued", "in_progress", "waiting", "pending", "requested"}
        and conclusion is None
    ):
        return "pending"
    if status != "completed":
        return "unknown"
    if conclusion == "success":
        return "success"
    if conclusion == "skipped":
        return "skipped"
    if conclusion in {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
    }:
        return "failure"
    return "unknown"


def ref_name(value):
    need(
        isinstance(value, str)
        and 0 < len(value) <= 150
        and all(ord(char) >= 33 for char in value)
        and not any(token in value for token in ["..", "\\", "?", "#", "@{", ":"]),
        "INVALID_BRANCH_REF",
    )
    return value


def pr_identity(raw):
    # Missing values remain errors; no inferred SHA, branch, draft or inventory item.
    return (
        raw["number"],
        raw["state"],
        raw["draft"],
        raw["head"]["sha"],
        raw["head"]["repo"]["full_name"],
        raw["base"]["ref"],
        raw["base"]["sha"],
        raw["base"]["repo"]["id"],
        raw["updated_at"],
    )


def compatibility(report):
    reasons = []
    if not report.observations_complete:
        reasons.append("COLLECTION_INCOMPLETE")
    if {pr.number for pr in report.pull_requests} != {24, 25, 26}:
        reasons.append("V01_CANNOT_REPRESENT_FULL_DYNAMIC_INVENTORY")
    if not report.repository or report.repository.default_branch != "main":
        reasons.append("V01_REQUIRES_MAIN")
    if any(pr.base_branch != "main" for pr in report.pull_requests):
        reasons.append("V01_CANNOT_REPRESENT_NON_MAIN_PR_BASE")
    if reasons:
        return Compatibility(
            target=TARGET,
            state="BLOCKED",
            reasons=reasons,
            payload=None,
            owner_authorization_verified=False,
        )
    repo = report.repository
    refs = {"head_sha": repo.default_sha, "base_sha": repo.default_sha, "base_branch": "main"}
    # Only the upstream data shape is projected; no Manager code or authorization logic is copied.
    payload = {
        "schema_version": "geointel-manager-input-v1",
        "evaluation_at": report.completed_at,
        "candidates": [],
        "snapshot": {
            **refs,
            "repository": repo.full_name,
            "private": True,
            "source_id": "github-state-collector",
            "source_ref": "urn:geointel:github-observations-v02",
            "provenance_status": "unverifiable",
            "captured_at": report.completed_at,
            "evidence": [
                {
                    **refs,
                    "id": "observed-default-refs",
                    "source_id": "github-state-collector",
                    "source_ref": "urn:geointel:github-observations-v02",
                    "observed_at": report.completed_at,
                    "topic": "repository_refs",
                    "subject": "default-refs",
                    "value": "api-observation-not-owner-attestation",
                    "status": "observed",
                }
            ],
            "assessments": [],
            "open_prs": [
                {
                    "number": pr.number,
                    "head_sha": pr.head_sha,
                    "state": "open",
                    "draft": pr.draft,
                    "resolution": "unresolved",
                }
                for pr in report.pull_requests
            ],
        },
    }
    return Compatibility(
        target=TARGET,
        state="STRUCTURAL_FIXTURE_COMPATIBLE_ONLY",
        reasons=["NO_OWNER_ATTESTATION", "NO_SCOPE_ASSESSMENTS_OR_TASKS"],
        payload=payload,
        owner_authorization_verified=False,
    )


def empty_snapshot(reader):
    now = stamp(reader.clock())
    return Snapshot(
        schema_version="geointel-github-observations-v0.2",
        state="BLOCKED",
        observations_complete=False,
        advisory=True,
        action_authorized=False,
        producer="geointel-github-collector/0.2",
        transport=reader.mode,
        started_at=now,
        completed_at=now,
        repository=None,
        ci_workflow=None,
        pull_requests=[],
        sources=[],
        issues=[],
        trust_boundary="api_metadata_observation_not_independent_review_or_owner_approval",
        content_digest=None,
        digest_role="integrity_only_not_authenticated_authorization",
        manager_v01=Compatibility(
            target=TARGET,
            state="BLOCKED",
            reasons=["NOT_COLLECTED"],
            payload=None,
            owner_authorization_verified=False,
        ),
    )


def collect(reader):
    report = empty_snapshot(reader)
    issues = []
    branches = {}

    def get(path, params=None):
        return reader.get(PREFIX + path, params)[0]

    def branch(name):
        ref_name(name)
        raw = get("/branches/" + quote(name, safe=""))
        need(raw["name"] == name, "BRANCH_IDENTITY_MISMATCH")
        return raw["commit"]["sha"]

    def inventory():
        values = reader.paginated(
            PREFIX + "/pulls",
            {
                "state": "open",
                "sort": "created",
                "direction": "asc",
            },
        )
        need(len(values) <= 25, "PR_INVENTORY_LIMIT")
        need(len({value["number"] for value in values}) == len(values), "DUPLICATE_PR_INVENTORY")
        return sorted(values, key=lambda value: value["number"])

    try:
        raw_repo = get("")
        need(
            raw_repo["id"] == 1375475901
            and raw_repo["full_name"] == "bur5/geointel"
            and raw_repo["private"] is True,
            "REPOSITORY_IDENTITY_OR_PRIVACY_MISMATCH",
        )
        default = ref_name(raw_repo["default_branch"])
        branches[default] = branch(default)
        report.repository = Repository(
            id=raw_repo["id"],
            full_name=raw_repo["full_name"],
            private=True,
            default_branch=default,
            default_sha=branches[default],
        )
        workflow = get("/actions/workflows/ci.yml")
        report.ci_workflow = Workflow(
            id=workflow["id"],
            path=workflow["path"],
            state=workflow["state"],
        )
        initial = inventory()
        for item in initial:
            number = item["number"]
            need(type(number) is int and number > 0, "INVALID_PR_NUMBER")
            pr = get(f"/pulls/{number}")
            need(pr_identity(pr) == pr_identity(item), f"PR_CHANGED_BEFORE_COLLECTION:{number}")
            need(pr["base"]["repo"]["id"] == report.repository.id, "PR_REPOSITORY_MISMATCH")
            observed = PullRequest(
                number=number,
                state=pr["state"],
                draft=pr["draft"],
                head_sha=pr["head"]["sha"],
                head_repository=pr["head"]["repo"]["full_name"],
                base_branch=pr["base"]["ref"],
                base_sha=pr["base"]["sha"],
                updated_at=pr["updated_at"],
                ci=None,
                reviews=[],
                content_handling="prose_excluded_from_snapshot_and_authority",
            )
            base = ref_name(pr["base"]["ref"])
            if base not in branches:
                branches[base] = branch(base)
            need(pr["base"]["sha"] == branches[base], f"STALE_PR_BASE:{number}")
            reviews_raw = reader.paginated(PREFIX + f"/pulls/{number}/reviews")
            reviews = []
            need(
                len({review["id"] for review in reviews_raw}) == len(reviews_raw),
                "DUPLICATE_REVIEW",
            )
            for value in sorted(reviews_raw, key=lambda value: value["id"]):
                review = Review(
                    id=value["id"],
                    user_id=value["user"]["id"],
                    login=value["user"]["login"],
                    user_type=value["user"]["type"],
                    state=value["state"],
                    commit_id=value["commit_id"],
                    submitted_at=value["submitted_at"],
                    stale_head=value["commit_id"] != pr["head"]["sha"],
                    historical_base_verified=False,
                    independence_verified=False,
                    owner_authorization_verified=False,
                )
                reviews.append(review)
                if review.stale_head or review.submitted_at is None or review.state == "PENDING":
                    issues.append(f"STALE_OR_INCOMPLETE_REVIEW:{number}:{review.id}")
            ci = collect_ci(reader, report.repository, report.ci_workflow, pr, issues)
            observed.ci = ci
            observed.reviews = reviews
            report.pull_requests.append(observed)
            reviews_after = reader.paginated(PREFIX + f"/pulls/{number}/reviews")

            def review_bindings(values):
                return sorted(
                    (v["id"], v["user"]["id"], v["state"], v["commit_id"], v["submitted_at"])
                    for v in values
                )

            need(
                review_bindings(reviews_after) == review_bindings(reviews_raw),
                f"REVIEWS_CHANGED_DURING_COLLECTION:{number}",
            )
            after = get(f"/pulls/{number}")
            need(pr_identity(after) == pr_identity(pr), f"PR_CHANGED_DURING_COLLECTION:{number}")
        final = inventory()
        need(
            [pr_identity(value) for value in final] == [pr_identity(value) for value in initial],
            "PR_INVENTORY_CHANGED",
        )
        for name, expected in branches.items():
            need(branch(name) == expected, "BASE_BRANCH_CHANGED_DURING_COLLECTION")
        final_workflow = get("/actions/workflows/ci.yml")
        need(
            (final_workflow["id"], final_workflow["path"], final_workflow["state"])
            == (workflow["id"], workflow["path"], workflow["state"]),
            "CI_WORKFLOW_CHANGED",
        )
        final_repo = get("")
        need(
            (
                final_repo["id"],
                final_repo["full_name"],
                final_repo["private"],
                final_repo["default_branch"],
            )
            == (raw_repo["id"], raw_repo["full_name"], True, default),
            "REPOSITORY_CHANGED",
        )
        reader.deadline()
    except CollectionError as error:
        issues.append(error.code)
    except (ValidationError, KeyError, TypeError, ValueError, OverflowError, AttributeError):
        # Never expose validation errors (which can embed raw API input).
        issues.append("MALFORMED_OR_CONFLICTING_API_DATA")
    report.issues = sorted(set(issues))
    report.sources = list(reader.sources)
    report.completed_at = stamp(reader.clock())
    # Metadata dates may be historical, but never future or internally reversed.
    end_time = datetime.strptime(report.completed_at, "%Y-%m-%dT%H:%M:%SZ")

    def check_dates(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.endswith("_at") and isinstance(child, str):
                    need(
                        datetime.strptime(child, "%Y-%m-%dT%H:%M:%SZ") <= end_time,
                        "FUTURE_METADATA_TIMESTAMP",
                    )
                else:
                    check_dates(child)
            if value.get("started_at") and value.get("completed_at"):
                need(value["started_at"] <= value["completed_at"], "REVERSED_METADATA_TIMESTAMPS")
        elif isinstance(value, list):
            for child in value:
                check_dates(child)

    try:
        check_dates(report.model_dump(exclude={"manager_v01"}))
    except (CollectionError, ValueError):
        report.issues = sorted(set(report.issues + ["INVALID_OR_FUTURE_METADATA_TIMESTAMPS"]))
    report.observations_complete = not report.issues
    report.state = "OBSERVED" if report.observations_complete else "BLOCKED"
    report.manager_v01 = compatibility(report)
    report.content_digest = digest(report.model_dump(exclude={"content_digest"}))
    return Snapshot.model_validate(report.model_dump())


def collect_ci(reader, repo, workflow, pr, issues):
    number = pr["number"]
    runs = reader.paginated(
        PREFIX + f"/actions/workflows/{workflow.id}/runs",
        {
            "head_sha": pr["head"]["sha"],
            "event": "pull_request",
        },
        key="workflow_runs",
    )
    candidates = [
        run
        for run in runs
        if run["head_sha"] == pr["head"]["sha"]
        and run["event"] == "pull_request"
        and run["workflow_id"] == workflow.id
    ]
    if not candidates:
        issues.append(f"MISSING_CI:{number}")
        return None
    need(len({run["id"] for run in candidates}) == len(candidates), "DUPLICATE_CI_RUN")
    selected = max(candidates, key=lambda run: run["id"])
    run = reader.get(PREFIX + f"/actions/runs/{selected['id']}")[0]
    association = next((value for value in run["pull_requests"] if value["number"] == number), None)
    need(
        run["id"] == selected["id"]
        and run["workflow_id"] == workflow.id
        and run["repository"]["id"] == repo.id
        and run["path"] == workflow.path
        and run["event"] == "pull_request"
        and run["head_sha"] == pr["head"]["sha"]
        and run["head_repository"]["full_name"] == pr["head"]["repo"]["full_name"]
        and association is not None
        and association["head"]["sha"] == pr["head"]["sha"]
        and association["base"]["sha"] == pr["base"]["sha"]
        and association["base"]["ref"] == pr["base"]["ref"],
        f"CI_BINDING_MISMATCH:{number}",
    )
    jobs_raw = reader.paginated(
        PREFIX + f"/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs",
        key="jobs",
    )
    need(len({job["id"] for job in jobs_raw}) == len(jobs_raw), "DUPLICATE_CI_JOB")
    if {job["name"] for job in jobs_raw} != CI_JOBS or len(jobs_raw) != len(CI_JOBS):
        issues.append(f"MISSING_OR_UNEXPECTED_CI_JOBS:{number}")
    jobs = []
    for value in sorted(jobs_raw, key=lambda job: (job["name"], job["id"])):
        url = value["check_run_url"]
        prefix = "https://api.github.com" + PREFIX + "/check-runs/"
        need(
            isinstance(url, str) and url.startswith(prefix) and url[len(prefix) :].isdigit(),
            "CHECK_SOURCE_URL_MISMATCH",
        )
        check_id = int(url[len(prefix) :])
        source = reader.get(PREFIX + f"/check-runs/{check_id}")[0]
        matched = (
            source["id"] == check_id
            and source["app"]["id"] == 15368
            and source["app"]["slug"] == "github-actions"
            and source["name"] == value["name"]
            and source["head_sha"] == value["head_sha"] == pr["head"]["sha"]
            and source["status"] == value["status"]
            and source["conclusion"] == value["conclusion"]
            and value["run_id"] == run["id"]
            and value["run_attempt"] == run["run_attempt"]
        )
        jobs.append(
            Job(
                id=value["id"],
                check_run_id=check_id,
                app_id=source["app"]["id"],
                app_slug=source["app"]["slug"],
                name=value["name"],
                head_sha=value["head_sha"],
                run_id=value["run_id"],
                attempt=value["run_attempt"],
                status=value["status"],
                conclusion=value["conclusion"],
                state=state(value["status"], value["conclusion"]),
                started_at=value["started_at"],
                completed_at=value["completed_at"],
                source_metadata_matched=matched,
                test_execution_independently_verified=False,
            )
        )
        if not matched:
            issues.append(f"UNTRUSTED_OR_CONFLICTING_CHECK:{number}:{check_id}")
        if jobs[-1].state != "success" or jobs[-1].completed_at is None:
            issues.append(f"CI_JOB_NOT_SUCCESSFUL_OR_INCOMPLETE:{number}:{check_id}")
    end = reader.get(PREFIX + f"/actions/runs/{run['id']}")[0]
    need(
        (end["run_attempt"], end["status"], end["conclusion"], end["head_sha"])
        == (run["run_attempt"], run["status"], run["conclusion"], run["head_sha"]),
        f"CI_CHANGED_DURING_COLLECTION:{number}",
    )
    ci = CI(
        run_id=run["id"],
        attempt=run["run_attempt"],
        workflow_id=workflow.id,
        path=run["path"],
        head_sha=run["head_sha"],
        reported_base_sha=association["base"]["sha"],
        reported_base_branch=association["base"]["ref"],
        status=run["status"],
        conclusion=run["conclusion"],
        state=state(run["status"], run["conclusion"]),
        created_at=run["created_at"],
        updated_at=run["updated_at"],
        historical_checkout_verified=False,
        jobs=jobs,
    )
    if ci.state != "success":
        issues.append(f"CI_RUN_NOT_SUCCESSFUL:{number}")
    return ci
