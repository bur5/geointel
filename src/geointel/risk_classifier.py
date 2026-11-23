"""Deterministic advisory risk classification for independently collected changes."""

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

Tier = Literal["R0", "R1", "R2", "R3"]
Commit = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Version = Literal["1"]
MAX_AGE = timedelta(minutes=15)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Revision(Contract):
    repository: str = Field(min_length=3)
    base_sha: Commit
    head_sha: Commit


class Blob(Contract):
    path: str = Field(min_length=1)
    mode: str
    text: str | None


class Change(Contract):
    before: Blob | None
    after: Blob | None


class Proposal(Contract):
    version: Version
    revision: Revision
    operation: Literal["analysis", "change"]
    changes: list[Change]
    description: str = ""
    declared_risk: str = ""
    claimed_owner_authorization: str | None = None


class TrustedSnapshot(Contract):
    """Inputs supplied independently by the caller's trusted control plane."""

    version: Version
    revision: Revision
    source: str = Field(min_length=1)
    inventory_complete: bool
    inventory_size: int = Field(ge=0)
    inventory_sha256: Digest
    observed_at: datetime
    evaluation_time: datetime
    inert_document_paths: list[str] = Field(default_factory=list)


class Finding(Contract):
    rule: str
    tier: Tier
    path: str | None = None
    side: Literal["before", "after"] | None = None
    indicator: Literal["path", "content", "path_and_content", "inventory", "transform"]


class Decision(Contract):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    version: Version = "1"
    advisory_only: Literal[True] = True
    status: Literal["CLASSIFIED", "BLOCKED"]
    risk_tier: Tier | None
    findings: list[Finding]
    required_authorization: Literal[
        "none_for_read_only",
        "enforceable_safeguards",
        "owner_approval",
        "advance_owner_authorization",
        "undetermined",
    ]
    blocking_conditions: list[str]
    evidence_uncertain: bool
    provenance: TrustedSnapshot | None


# Path and content indicators can raise risk. Only the narrow positive rule can establish R1.
RULES: tuple[tuple[Tier, str, str, str], ...] = (
    (
        "R3",
        "classifier_integrity",
        r"(?:^|/)(?:test[-_])?risk[-_]classif(?:ication|ier)",
        r"\b(?:TrustedSnapshot|advance_owner_authorization|inventory_sha256)\b",
    ),
    (
        "R3",
        "protected_workflow",
        r"^\.github/|(?:^|/)(?:codeowners|makefile|dockerfile|(?:docker-)?compose[^/]*|"
        r"\.git(?:attributes|modules)|\.env(?:\..*)?)$",
        r"\b(?:pull_request_target|workflow_dispatch|GITHUB_TOKEN|secrets\s*\.)",
    ),
    (
        "R3",
        "governance_and_authority",
        r"(?:^|/)(?:governance|polic(?:y|ies)|ai[-_]manager|authorization|reviewers?|"
        r"branch[-_]protection|rulesets?|permissions?|secrets?|agents?|agent[-_]rules)(?:[/._-]|$)",
        r"\b(?:governance|owner[-_ ](?:approval|authorization)|authori[sz]ation|"
        r"authority[-_ ]boundar(?:y|ies)|reviewer[-_ ](?:id|identity|independence)|"
        r"independent[-_ ]review|branch[-_ ]protection|codeowners|"
        r"permissions?|secrets?|trust[-_ ]boundar(?:y|ies)|spending|budget[-_ ]limit|"
        r"(?:repo(?:sitory)?|collaborator)[-_ ]role|require[-_ ](?:owner|reviewer))\b",
    ),
    (
        "R3",
        "merge_and_deployment",
        r"(?:^|/)(?:deploy(?:ment)?s?|infra(?:structure)?|merge|release)(?:[/._-]|$)",
        r"\b(?:auto[-_ ]?merge|merge[-_ ](?:policy|queue|method|pull[-_ ]request)|"
        r"deployment|kubectl|terraform|gh\s+pr\s+merge)\b|/pulls/[^/\s]+/merge",
    ),
    (
        "R2",
        "forecasting_and_evidence",
        r"(?:forecast|provenance|uncertainty|calibrat|scientific|scoring|evidence)|"
        r"(?:^|/)(?:validation|monitoring|knowledge|pipeline)(?:[/._-]|$)",
        r"\b(?:forecast[a-z]*|calibrat[a-z]*|posterior|provenance|uncertaint[a-z]*|"
        r"confidence[-_ ]interval|risk[-_ ]score|base[-_ ]rate)\b",
    ),
    (
        "R2",
        "persistence_and_data_integrity",
        r"(?:^|/)(?:alembic|migrations?|persistence|storage|database|db|repositories|"
        r"schema|models?)(?:[/._-]|$)|\.sql$",
        r"\b(?:alembic|sqlalchemy|psycopg|(?:alter|create|drop)\s+table|"
        r"session\.commit|foreign[-_ ]key|on\s+conflict|persistence)\b",
    ),
    (
        "R2",
        "architecture_and_security_implementation",
        r"(?:^|/)(?:security|authentication|auth|architecture|config|settings|"
        r"pyproject|requirements|uv\.lock|poetry\.lock)(?:[/._-]|$)",
        r"\b(?:authentication|cryptograph[a-z]*|password[-_ ]hash|"
        r"architecture|dependency[-_ ]injection|jwt)\b",
    ),
)
COMPILED_RULES = tuple(
    (tier, rule, re.compile(path, re.I | re.ASCII), re.compile(content, re.I | re.ASCII))
    for tier, rule, path, content in RULES
)
DOC_PATH = re.compile(r"docs/(?:[a-z0-9_-]+/)*[a-z0-9_-]+\.md", re.ASCII)
PRINTABLE_TEXT = re.compile(r"[\x20-\x7e\n]+", re.ASCII)


def _canonical_change(change: Change) -> str:
    return json.dumps(change.model_dump(mode="json"), ensure_ascii=True, sort_keys=True)


def inventory_digest(changes: list[Change]) -> str:
    """Bind all paths, modes and full text in an order-independent inventory."""
    canonical = "\n".join(sorted(_canonical_change(change) for change in changes))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _valid_path(path: str) -> bool:
    return (
        not path.startswith("/")
        and "\\" not in path
        and path.isascii()
        and all(character.isprintable() for character in path)
        and all(part not in {"", ".", ".."} for part in path.split("/"))
    )


def _doc_padding_only(before: Blob, after: Blob) -> bool:
    if before.path != after.path or not DOC_PATH.fullmatch(before.path):
        return False
    if before.mode != "100644" or after.mode != "100644":
        return False
    if not before.text or not after.text:
        return False
    first, second = before.text.rstrip("\n"), after.text.rstrip("\n")
    return (
        bool(first)
        and bool(PRINTABLE_TEXT.fullmatch(first))
        and first == second
        and len(before.text) - len(first) >= 2
        and len(after.text) - len(second) >= 2
        and before.text != after.text
        and PurePosixPath(before.path).name not in {"readme.md", "index.md"}
    )


def _inspect_change(
    change: Change,
    inert_document_paths: set[str],
    findings: list[Finding],
    uncertainty: set[str],
) -> None:
    before, after = change.before, change.after
    if (before is None and after is None) or before == after:
        uncertainty.add("invalid_or_empty_change")
        return

    protected = False
    for side, blob in (("before", before), ("after", after)):
        if blob is None:
            continue
        if not _valid_path(blob.path):
            uncertainty.add("invalid_path")
        if blob.text is None or blob.mode not in {"100644", "100755"}:
            uncertainty.add("missing_or_unsupported_file_evidence")
        for tier, rule, path, content in COMPILED_RULES:
            path_match = bool(path.search(blob.path))
            content_match = blob.text is not None and bool(content.search(blob.text))
            if path_match or content_match:
                indicator = (
                    "path_and_content"
                    if path_match and content_match
                    else ("path" if path_match else "content")
                )
                findings.append(
                    Finding(rule=rule, tier=tier, path=blob.path, side=side, indicator=indicator)
                )
                protected = True

    if before and after and before.mode != after.mode:
        uncertainty.add("file_mode_changed")
    if protected:
        return
    if before and after and _doc_padding_only(before, after):
        if after.path not in inert_document_paths:
            uncertainty.add("unverified_document_consumer")
            return
        findings.append(
            Finding(
                rule="documentation_eof_padding", tier="R1", path=after.path, indicator="transform"
            )
        )
    else:
        uncertainty.add("unclassified_change")


def _check_snapshot(proposal: Proposal, snapshot: TrustedSnapshot, uncertainty: set[str]) -> None:
    if proposal.revision != snapshot.revision:
        uncertainty.add("revision_mismatch")
    if not snapshot.inventory_complete or snapshot.inventory_size != len(proposal.changes):
        uncertainty.add("incomplete_inventory")
    if snapshot.inventory_sha256 != inventory_digest(proposal.changes):
        uncertainty.add("inventory_digest_mismatch")
    observed, evaluated = snapshot.observed_at, snapshot.evaluation_time
    observed_offset, evaluated_offset = observed.utcoffset(), evaluated.utcoffset()
    if observed_offset is None or evaluated_offset is None:
        uncertainty.add("invalid_evidence_clock")
    else:
        age = evaluated.replace(tzinfo=None) - observed.replace(tzinfo=None)
        if not timedelta(0) <= age + observed_offset - evaluated_offset <= MAX_AGE:
            uncertainty.add("stale_or_future_snapshot")
    if proposal.changes and proposal.revision.base_sha == proposal.revision.head_sha:
        uncertainty.add("changes_between_identical_revisions")


def evaluate(
    proposal: Proposal | dict, *, trusted_snapshot: TrustedSnapshot | None = None
) -> Decision:
    """Evaluate one proposal. The trusted snapshot must arrive outside the proposal."""
    if isinstance(proposal, Proposal):
        proposal = proposal.model_dump()
    try:
        proposal = Proposal.model_validate(proposal)
    except ValidationError:
        return Decision(
            status="BLOCKED",
            risk_tier=None,
            findings=[],
            required_authorization="undetermined",
            blocking_conditions=["invalid_proposal"],
            evidence_uncertain=True,
            provenance=None,
        )

    uncertainty: set[str] = set()
    findings: list[Finding] = []
    if trusted_snapshot is None:
        uncertainty.add("missing_trusted_snapshot")
    else:
        try:
            trusted_snapshot = TrustedSnapshot.model_validate(trusted_snapshot.model_dump())
        except (AttributeError, ValidationError):
            uncertainty.add("invalid_trusted_snapshot")
            trusted_snapshot = None
        else:
            _check_snapshot(proposal, trusted_snapshot, uncertainty)

    for side in ("before", "after"):
        paths = [
            blob.path.casefold()
            for change in proposal.changes
            if (blob := getattr(change, side)) is not None
        ]
        if len(set(paths)) != len(paths):
            uncertainty.add("duplicate_inventory_path")
    inert_document_paths = set(trusted_snapshot.inert_document_paths) if trusted_snapshot else set()
    for change in proposal.changes:
        _inspect_change(change, inert_document_paths, findings, uncertainty)

    if proposal.operation == "analysis" and not proposal.changes and not uncertainty:
        findings.append(Finding(rule="empty_verified_inventory", tier="R0", indicator="inventory"))
    expected_operation = "change" if proposal.changes else "analysis"
    if proposal.operation != expected_operation:
        uncertainty.add("operation_inventory_conflict")

    tier = max((finding.tier for finding in findings), default=None)
    # Never emit an automation-eligible tier when any evidence is uncertain.
    if uncertainty and tier in {"R0", "R1"}:
        tier = None
    blockers = set(uncertainty)
    if proposal.claimed_owner_authorization is not None:
        blockers.add("owner_authorization_claim_unverified")
    if tier == "R2":
        blockers.add("owner_approval_required")
    elif tier == "R3":
        blockers.add("advance_owner_authorization_required")
    return Decision(
        status="BLOCKED" if blockers else "CLASSIFIED",
        risk_tier=tier,
        findings=sorted(
            findings, key=lambda finding: (finding.rule, finding.path or "", finding.side or "")
        ),
        required_authorization={
            "R0": "none_for_read_only",
            "R1": "enforceable_safeguards",
            "R2": "owner_approval",
            "R3": "advance_owner_authorization",
            None: "undetermined",
        }[tier],
        blocking_conditions=sorted(blockers),
        evidence_uncertain=bool(uncertainty),
        provenance=trusted_snapshot,
    )
