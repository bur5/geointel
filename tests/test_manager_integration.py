import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from geointel.manager_integration import (
    COLLECTOR_REVISION,
    ContractError,
    ManagerInput,
    prepare_manager_input,
)

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "manager_integration"
ORIGINAL = "2026-11-13T12:00:00Z"
SECOND = "2026-11-13T12:00:01Z"
NOW = datetime(2026, 11, 13, 12, 0, 1, tzinfo=UTC)


def fixture(name="native_v02"):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def with_digest(raw):
    body = {key: value for key, value in raw.items() if key != "content_digest"}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return {**body, "content_digest": digest}


def snapshots():
    first = fixture()
    second = deepcopy(first)
    second.update(started_at=SECOND, completed_at=SECOND)
    for source in second["sources"]:
        source.update(received_at=SECOND, server_date=SECOND)
    return first, second


def evaluate(first, second, *, now=NOW, revision=COLLECTOR_REVISION):
    reads = iter([with_digest(first), with_digest(second)])
    return prepare_manager_input(reads.__next__, collector_revision=revision, clock=lambda: now)


def test_dynamic_native_migration_is_deterministic():
    first, second = snapshots()
    result = evaluate(first, second)
    assert result == evaluate(first, second)
    assert [pr.number for pr in result.observed_github.pull_requests] == [24, 25]
    main, release = result.observed_github.pull_requests
    assert main.base_branch == "main"
    assert release.base_branch == "release/stable"
    assert main.base_sha != release.base_sha
    assert release.draft
    assert len(release.ci.jobs) == 3
    assert result.revalidation.sources
    assert result.recommendation_authority == "advisory_only"
    assert result.authenticated_owner_decision is None
    assert not result.autonomous_merge_enabled
    assert not result.action_authorized


def test_new_inventory_and_empty_inventory_are_representable():
    first, second = snapshots()
    for report in (first, second):
        report["pull_requests"][1]["number"] = 42
        for source in report["sources"]:
            source["endpoint"] = source["endpoint"].replace("/pulls/25", "/pulls/42")
    assert [pr.number for pr in evaluate(first, second).observed_github.pull_requests] == [24, 42]
    for report in (first, second):
        report["pull_requests"] = []
        report["sources"] = [
            source
            for source in report["sources"]
            if source["endpoint"].split("/")[-1] in {"geointel", "pulls", "ci.yml", "main"}
        ]
        for idx, source in enumerate(report["sources"], 1):
            source["sequence"] = idx
    assert evaluate(first, second).observed_github.pull_requests == []


@pytest.mark.parametrize("field", ["head_sha", "base_sha", "base_branch", "draft"])
def test_changed_candidate_between_captures_blocks(field):
    first, second = snapshots()
    pr = second["pull_requests"][1]
    if field == "draft":
        pr[field] = not pr[field]
    elif field == "head_sha":
        previous = pr[field]
        pr[field] = pr["ci"][field] = "e" * 40
        for job in pr["ci"]["jobs"]:
            job[field] = pr[field]
        for source in second["sources"]:
            if source["query"].get("head_sha") == previous:
                source["query"]["head_sha"] = pr[field]
    elif field == "base_sha":
        pr[field] = pr["ci"]["reported_base_sha"] = "e" * 40
    else:
        pr[field] = pr["ci"]["reported_base_branch"] = "other"
        for source in second["sources"]:
            source["endpoint"] = source["endpoint"].replace("release%2Fstable", "other")
    with pytest.raises(ContractError, match="OBSERVATION_CHANGED"):
        evaluate(first, second)


def test_omitted_inventory_item_with_remaining_source_blocks():
    first, second = snapshots()
    second["pull_requests"].pop()
    with pytest.raises(ContractError, match="INVENTORY_PROVENANCE_MISMATCH"):
        evaluate(first, second)


@pytest.mark.parametrize("state", ["APPROVED", "COMMENTED", "DISMISSED", "CHANGES_REQUESTED"])
def test_reviews_and_legacy_approval_claims_are_advisory(state):
    first, second = snapshots()
    for report in (first, second):
        pr = report["pull_requests"][0]
        pr["reviews"].append(
            {
                "id": 3,
                "user_id": 4,
                "login": "codex",
                "user_type": "Bot",
                "state": state,
                "commit_id": pr["head_sha"],
                "submitted_at": ORIGINAL,
                "stale_head": False,
                "historical_base_verified": False,
                "independence_verified": False,
                "owner_authorization_verified": False,
            }
        )
        report["manager_v01"]["payload"] = {"owner": "APPROVED", "manager_risk": "R0"}
    result = evaluate(first, second)
    assert result.observed_github.pull_requests[0].reviews[0].state == state
    assert result.authenticated_owner_decision is None
    assert "manager_risk" not in result.model_dump_json()
    second["pull_requests"][0]["reviews"].clear()
    with pytest.raises(ContractError, match="OBSERVATION_CHANGED"):
        evaluate(first, second)
    first["pull_requests"][0]["reviews"][0]["commit_id"] = "f" * 40
    with pytest.raises(ContractError, match="REVIEW_BINDING_MISMATCH"):
        evaluate(first, second)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda raw: raw.update(transport="mock"), "UNSUPPORTED_COLLECTOR"),
        (lambda raw: raw.update(issues=["API_DENIED"]), "INCOMPLETE_OBSERVATION"),
        (lambda raw: raw.update(observations_complete=False), "INCOMPLETE_OBSERVATION"),
        (lambda raw: raw.pop("sources"), "INVALID_OBSERVATION"),
        (lambda raw: raw.update(sources=raw["sources"][:-1]), "MISSING_RECHECK_PROVENANCE"),
        (
            lambda raw: raw["sources"][0].update(server_date="2026-11-13T12:00:99Z"),
            "INVALID_OBSERVATION",
        ),
        (lambda raw: raw["repository"].update(private=1), "INVALID_OBSERVATION"),
        (
            lambda raw: [source["query"].pop("head_sha", None) for source in raw["sources"]],
            "MISSING_CI_LOOKUP_PROVENANCE",
        ),
        (lambda raw: raw["pull_requests"].append(raw["pull_requests"][0]), "DUPLICATE_PR"),
        (lambda raw: raw["pull_requests"][1].update(base_branch="main"), "BASE_CONFLICT"),
        (
            lambda raw: raw["pull_requests"][0]["ci"].update(reported_base_sha="e" * 40),
            "CI_BINDING_MISMATCH",
        ),
        (lambda raw: raw["pull_requests"][0]["ci"]["jobs"].pop(), "INVALID_OBSERVATION"),
        (
            lambda raw: raw["pull_requests"][0]["ci"]["jobs"][0].update(attempt=2),
            "JOB_BINDING_MISMATCH",
        ),
        (
            lambda raw: raw["pull_requests"][0]["ci"].update(conclusion="skipped"),
            "INVALID_OBSERVATION",
        ),
        (lambda raw: raw["pull_requests"][0]["ci"].update(conclusion=None), "INVALID_OBSERVATION"),
    ],
)
def test_incomplete_or_conflicting_evidence(change, reason):
    first, second = snapshots()
    change(first)
    with pytest.raises(ContractError, match=reason):
        evaluate(first, second)


def test_stale_future_replayed_or_wrong_revision():
    first, second = snapshots()
    for now in (NOW - timedelta(seconds=2), NOW + timedelta(minutes=6)):
        with pytest.raises(ContractError, match="STALE_OR_FUTURE_OBSERVATION"):
            evaluate(first, second, now=now)
    with pytest.raises(ContractError, match="STALE_OR_REPLAYED_OBSERVATION"):
        evaluate(first, first)
    with pytest.raises(ContractError, match="UNSUPPORTED_COLLECTOR_REVISION"):
        evaluate(first, second, revision="f" * 40)


def test_offline_legacy_fixture_cannot_supply_native_evidence():
    with pytest.raises(ContractError, match="UNSUPPORTED_COLLECTOR"):
        evaluate(fixture("legacy_v01"), snapshots()[1])


def test_integrity_is_checked_and_source_errors_are_sanitized():
    first, _ = snapshots()
    raw = with_digest(first)
    raw["repository"]["default_sha"] = "c" * 40
    with pytest.raises(ContractError, match="INTEGRITY_MISMATCH"):
        prepare_manager_input(lambda: raw, collector_revision=COLLECTOR_REVISION, clock=lambda: NOW)

    def bad_read():
        raise RuntimeError("PRIVATE_PAYLOAD")

    with pytest.raises(ContractError, match="^OBSERVATION_UNAVAILABLE$"):
        prepare_manager_input(bad_read, collector_revision=COLLECTOR_REVISION, clock=lambda: NOW)


def test_published_schema_matches_model():
    schema = ROOT / "docs" / "manager-input-v03.schema.json"
    assert json.loads(schema.read_text()) == ManagerInput.model_json_schema()
