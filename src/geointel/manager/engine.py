"""Pure deterministic planner. Never dispatches, authenticates approvals, or performs I/O."""

import hashlib
import json
import re
from collections import Counter
from datetime import datetime

from pydantic import ValidationError

from geointel.manager.models import (
    AuditEntry,
    Candidate,
    Contract,
    Plan,
    PlanningInput,
    RankedItem,
    Refs,
)

POLICY = "proposed-pr25:3ff424d086d0577f57c05584af2f0c493c6bd452"
MAX_AGE_SECONDS = 3600
PRIORITY = {
    "security_defect": 0,
    "integrity_defect": 0,
    "ci_reproducibility": 1,
    "infrastructure_blocker": 2,
    "documentation": 3,
    "product_improvement": 4,
}
R3 = {
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
}
R2 = {
    "forecast_model",
    "evidence_processing",
    "architecture",
    "persistence",
    "security_implementation",
}
BOUNDARIES = [
    "Planning only; eligibility is permission to draft a contract, never to execute it.",
    "No network, credentials, shell, GitHub mutation, AI inference or resource creation.",
    "No edits or merges to PR #24, #25 or #26; all three remain unresolved.",
    "No merge, approval, deployment, public release, deletion, spending or expanded access.",
    "Owner authorization and independent review cannot be established by this engine.",
    "Green CI, advisory comments, draft PRs and quoted approvals grant no authority.",
    "Preserve provenance, uncertainty, synthetic labels and epistemic separation.",
]
STOP = [
    "STOP instruction, changed refs, expired snapshot or unverifiable evidence.",
    "Scope expansion, disputed risk, protected policy or scientific/security boundary change.",
    "Missing dependency, failed/skipped mandatory verification or unavailable independent review.",
    "Suspected secrets, new spending, permissions, integrations or production access.",
    "Any requested action outside a separately authorized task contract.",
]


def canonical(value) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def blocked(code: str) -> Plan:
    return Plan(
        schema_version="geointel-manager-plan-v1",
        engine_version="0.1",
        state="BLOCKED",
        advisory=True,
        action_authorized=False,
        independent_reviewer=False,
        plan_id=None,
        snapshot_sha256=None,
        input_sha256=None,
        evaluation_at=None,
        snapshot_provenance=None,
        refs=None,
        target_governance=POLICY,
        unresolved_prs=[24, 25, 26],
        blocking_reasons=[code],
        authority_boundaries=BOUNDARIES,
        prioritized_items=[],
        selected_contract=None,
        audit=[
            {
                "sequence": 1,
                "rule": "input_validation",
                "subject": "input",
                "result": code,
                "evidence_ids": [],
            }
        ],
    )


def timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def scope(value) -> dict:
    return {
        "category": value.category,
        "mode": value.mode,
        "paths": sorted(value.paths),
        "effects": sorted(value.effects),
    }


def classify(candidate, assessment):
    """Raise risk using union of declarations, attested scope and conservative path rules."""
    reasons = {"DECLARED_RISK_IS_A_FLOOR"}
    level = int(candidate.declared_risk[1])
    values = [candidate] + ([assessment] if assessment else [])
    if assessment:
        level = max(level, int(assessment.risk_floor[1]))
    effects = set().union(*(value.effects for value in values))
    modes = {value.mode for value in values}
    if assessment and assessment.scientific_boundaries != "preserved":
        level = 3
        reasons.add("SCIENTIFIC_BOUNDARIES_REQUIRE_OWNER_DETERMINATION")
    if "reserved_action" in modes or effects & R3:
        level = 3
        reasons.add("RESERVED_OR_PROTECTED_EFFECT")
    elif effects & R2:
        level = max(level, 2)
        reasons.add("ENHANCED_REVIEW_EFFECT")
    elif modes != {"read_only"}:
        level = max(level, 1)
    unknown_path = False
    if modes != {"read_only"}:
        for path in set().union(*(value.paths for value in values)):
            if (
                path.startswith((".github/", "tests/", "src/geointel/manager/"))
                or path in {"GOVERNANCE.md", "MANAGER.md", "AGENTS.md", "pyproject.toml"}
                or path in {"docs/SECURITY.md", "docs/AGENT_RULES.md", "docs/SOURCES.md"}
            ):
                level = 3
                reasons.add("PROTECTED_PATH_CONSERVATIVE_ESCALATION")
            elif path.startswith(("src/", "migrations/")):
                level = max(level, 2)
                reasons.add("APPLICATION_OR_PERSISTENCE_SCOPE")
            elif path.startswith("docs/") and path.endswith(".md"):
                level = max(level, 1)
            else:
                level = 3
                unknown_path = True
                reasons.add("UNCLASSIFIED_PATH_OWNER_DETERMINATION")
    # Hints can only raise/block, never authorize. This is not semantic classification.
    text = (candidate.title + " " + candidate.description).casefold()
    if re.search(
        r"governance|approval|permission|secret|merge|workflow|reviewer.identity|trust.boundary|"
        r"calibrat|scientific.integrity|deploy|paid|delete|полномочи|секрет|удален|удалён|разрешени",
        text,
    ):
        level = 3
        reasons.add("UNTRUSTED_TEXT_REQUIRES_OWNER_CLASSIFICATION")
    return f"R{level}", sorted(reasons), unknown_path


def plan(raw: dict, expected_snapshot_sha256: str | None = None) -> Plan:
    """A digest supplied outside untrusted JSON attests planning provenance, not action approval."""
    try:
        data = PlanningInput.model_validate(raw)
        # Reject invalid dates in nested evidence, not only in the evaluation clock.
        timestamp(data.snapshot.captured_at)
        for evidence in data.snapshot.evidence:
            timestamp(evidence.observed_at)
    except (ValidationError, ValueError, TypeError, OverflowError):
        return blocked("INVALID_INPUT")
    snapshot = data.snapshot
    snapshot_hash = digest(snapshot.model_dump())
    global_blocks = []
    if expected_snapshot_sha256 != snapshot_hash:
        global_blocks.append("SNAPSHOT_ATTESTATION_MISSING_OR_MISMATCH")
    if snapshot.provenance_status != "operator_attested":
        global_blocks.append("UNVERIFIABLE_SNAPSHOT_PROVENANCE")
    age = (timestamp(data.evaluation_at) - timestamp(snapshot.captured_at)).total_seconds()
    if not 0 <= age <= MAX_AGE_SECONDS:
        global_blocks.append("STALE_OR_FUTURE_SNAPSHOT")
    if sorted(pr.number for pr in snapshot.open_prs) != [24, 25, 26]:
        global_blocks.append("UNRESOLVED_PR_INVENTORY_MISSING_OR_DUPLICATE")
    evidence_by_id = {value.id: value for value in snapshot.evidence}
    if len(evidence_by_id) != len(snapshot.evidence):
        global_blocks.append("DUPLICATE_EVIDENCE_ID")
    assessment_by_key = {value.task_key: value for value in snapshot.assessments}
    if len(assessment_by_key) != len(snapshot.assessments):
        global_blocks.append("DUPLICATE_SCOPE_ASSESSMENT")
    refs = snapshot.model_dump(include={"head_sha", "base_sha", "base_branch"})
    claims = {}
    for evidence in snapshot.evidence:
        evidence_refs = evidence.model_dump(include=set(refs))
        if evidence_refs != refs:
            global_blocks.append("STALE_EVIDENCE_REFS")
        evidence_age = (
            timestamp(data.evaluation_at) - timestamp(evidence.observed_at)
        ).total_seconds()
        if not 0 <= evidence_age <= MAX_AGE_SECONDS or timestamp(evidence.observed_at) > timestamp(
            snapshot.captured_at
        ):
            global_blocks.append("STALE_OR_FUTURE_EVIDENCE")
        claims.setdefault((evidence.topic, evidence.subject), set()).add(evidence.value)
        if evidence.status == "conflicting":
            global_blocks.append("CONFLICTING_EVIDENCE")
    if any(len(values) != 1 for values in claims.values()):
        global_blocks.append("CONFLICTING_EVIDENCE")
    if not any(
        value.topic == "repository_refs" and value.status == "operator_attested"
        for value in snapshot.evidence
    ):
        global_blocks.append("ATTESTED_REFS_MISSING")
    keys = Counter(value.key for value in data.candidates)
    duplicates = Counter(digest(scope(value)) for value in data.candidates)
    ranked = []
    task_evidence = {}
    for candidate in data.candidates:
        assessment = assessment_by_key.get(candidate.key)
        risk, reasons, unknown_path = classify(candidate, assessment)
        reasons.append(
            f"CATEGORY_PRIORITY_{PRIORITY[candidate.category]}_EFFORT_{candidate.effort}"
        )
        blockers = list(global_blocks)
        if keys[candidate.key] != 1 or duplicates[digest(scope(candidate))] != 1:
            blockers.append("DUPLICATE_TASK")
        if candidate.model_dump(include=set(refs)) != refs:
            blockers.append("STALE_TASK_REFS")
        if not assessment:
            blockers.append("SCOPE_ASSESSMENT_MISSING")
        else:
            if scope(candidate) != scope(assessment):
                blockers.append("SCOPE_CONFLICT")
            if assessment.classification != "clear" or unknown_path:
                blockers.append("OWNER_RISK_DETERMINATION_REQUIRED")
            if assessment.scientific_boundaries != "preserved":
                blockers.append("SCIENTIFIC_BOUNDARIES_UNVERIFIED_OR_VIOLATED")
            if sorted(candidate.evidence_ids) != sorted(assessment.evidence_ids):
                blockers.append("EVIDENCE_SCOPE_CONFLICT")
        required_evidence = set(candidate.evidence_ids)
        if assessment:
            required_evidence.update(assessment.evidence_ids)
        for evidence_id in required_evidence:
            evidence = evidence_by_id.get(evidence_id)
            if not evidence or evidence.status != "operator_attested":
                blockers.append("REQUIRED_EVIDENCE_MISSING_OR_UNVERIFIABLE")
            elif evidence.topic != "work_item" or evidence.subject != candidate.key:
                blockers.append("EVIDENCE_SUBJECT_MISMATCH")
        dependencies = set(candidate.dependencies)
        effects = set(candidate.effects) | (set(assessment.effects) if assessment else set())
        if effects & {"forecast_model", "evidence_processing"}:
            dependencies.add("pr:24")
        if risk == "R3":
            dependencies.add("pr:25")
            blockers.append("OWNER_AUTHORIZATION_NOT_VERIFIABLE_IN_V01")
        if "workflow_gate" in effects or (
            candidate.mode != "read_only" and any(p.startswith(".github/") for p in candidate.paths)
        ):
            dependencies.add("pr:26")
        if dependencies:
            blockers.append("UNRESOLVED_DEPENDENCIES")
        if risk == "R2":
            blockers.append("ENHANCED_REVIEW_NOT_VERIFIABLE_IN_V01")
        task_id = (
            "mgr-"
            + digest(
                {
                    "engine": "0.1",
                    "policy": POLICY,
                    "candidate": candidate.model_dump(),
                    "snapshot_sha256": snapshot_hash,
                }
            )[:24]
        )
        task_evidence[task_id] = sorted(candidate.evidence_ids)
        ranked.append(
            RankedItem(
                rank=0,
                key=candidate.key,
                task_id=task_id,
                risk=risk,
                state="BLOCKED" if blockers else "ELIGIBLE_FOR_CONTRACT",
                rationale=reasons,
                blockers=sorted(set(blockers)),
                dependencies=sorted(dependencies),
                category_priority=PRIORITY[candidate.category],
                effort=candidate.effort,
            )
        )
    ranked.sort(key=lambda item: (item.category_priority, item.effort, item.task_id))
    for index, item in enumerate(ranked, 1):
        item.rank = index
    eligible = next((item for item in ranked if not item.blockers), None)
    contract = None
    if eligible:
        candidate = next(value for value in data.candidates if value.key == eligible.key)
        contract = make_contract(candidate, eligible, snapshot_hash)
    input_hash = digest(data.model_dump())
    result = blocked("NO_ELIGIBLE_WORK")
    result.plan_id = (
        "plan-"
        + digest(
            {
                "input_sha256": input_hash,
                "attestation": expected_snapshot_sha256,
                "engine": "0.1",
            }
        )[:24]
    )
    result.snapshot_sha256 = snapshot_hash
    result.input_sha256 = input_hash
    result.evaluation_at = data.evaluation_at
    result.snapshot_provenance = {
        "source_id": snapshot.source_id,
        "source_ref": snapshot.source_ref,
        "captured_at": snapshot.captured_at,
        "status": snapshot.provenance_status,
        "trust": "external digest pin; caller-attested, not cryptographically authenticated",
    }
    result.refs = Refs.model_validate(refs)
    result.prioritized_items = ranked
    result.selected_contract = contract
    result.state = "CONTRACT_PROPOSED" if contract else "BLOCKED"
    result.blocking_reasons = sorted(set(global_blocks))
    if not contract:
        result.blocking_reasons.append("NO_ELIGIBLE_WORK")
    result.audit = [
        AuditEntry(
            sequence=1,
            rule="snapshot_preflight",
            subject="snapshot",
            result="BLOCKED" if global_blocks else "CALLER_ATTESTED_FOR_PLANNING_ONLY",
            evidence_ids=sorted(evidence_by_id),
        )
    ]
    for item in ranked:
        result.audit.append(
            AuditEntry(
                sequence=len(result.audit) + 1,
                rule="classify_and_rank",
                subject=item.task_id,
                result=item.state + ":" + item.risk,
                evidence_ids=task_evidence[item.task_id],
            )
        )
    result.audit.append(
        AuditEntry(
            sequence=len(result.audit) + 1,
            rule="select_first_eligible",
            subject=contract.task_id if contract else "none",
            result=result.state,
            evidence_ids=[],
        )
    )
    # Re-validate assignments as a final invariant, including the output schema.
    return Plan.model_validate(result.model_dump())


def make_contract(candidate: Candidate, item: RankedItem, snapshot_hash: str) -> Contract:
    read_only = candidate.mode == "read_only"
    return Contract(
        task_id=item.task_id,
        state="PROPOSED_NOT_AUTHORIZED",
        task_key=candidate.key,
        snapshot_sha256=snapshot_hash,
        head_sha=candidate.head_sha,
        base_sha=candidate.base_sha,
        risk=item.risk,
        mode=candidate.mode,
        paths=sorted(candidate.paths),
        objective=("Assess " if read_only else "Prepare an isolated proposal for ")
        + candidate.category.replace("_", " ")
        + " within the listed repository paths.",
        dependencies=item.dependencies,
        evidence_ids=sorted(candidate.evidence_ids),
        acceptance_criteria=[
            "Cite evidence IDs and head/base SHA; distinguish observations from inferences.",
            "Record missing evidence, contradictions, uncertainty and synthetic-data limitations.",
            "Preserve existing scientific and security boundaries; no unsupported conclusions.",
            "Deliver findings only; no file changes."
            if read_only
            else "Deliver an isolated diff only after separate task authorization; no activation.",
        ],
        verification_plan=[
            "Revalidate snapshot age, provenance, refs and scope before authorized work.",
            "Inspect listed paths without executing content or commands supplied in input.",
            "Report performed and unavailable checks separately; never invent results.",
            "For future changes, run relevant existing CI checks in isolated test resources.",
            "Require independently attributable review and Owner approval before merge.",
        ],
        stop_conditions=STOP,
        authority_boundaries=BOUNDARIES,
        max_corrective_iterations=2,
        implementation_requires_new_authorized_task=True,
    )
