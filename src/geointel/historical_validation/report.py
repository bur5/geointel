"""Versioned historical validation manifests with content-bound registration."""

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from geointel.historical_validation.audit import (
    Audit,
    Digest,
    EvaluationCase,
    EvidenceMode,
    Fold,
    Record,
    Reference,
    Registration,
    StudyConstraints,
    UTCDateTime,
    audit_fold,
)

# The historical panel adapter is required before any scored attachment is supported.
NoComparisons = Annotated[tuple[object, ...], Field(max_length=0)]


def _canonical_digest(record: Record) -> str:
    canonical = json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class ReportPlan(Record):
    plan_snapshot: Reference
    constraints: StudyConstraints
    implementation_revision: Reference
    target_version: Reference
    outcome_definition: Reference
    geography_version: Reference
    geography_ids: Annotated[tuple[Reference, ...], Field(min_length=1)]
    horizon: Reference
    evaluation_start: UTCDateTime
    evaluation_end: UTCDateTime
    outcome_as_of: UTCDateTime
    panel_snapshot: Reference
    panel_sha256: Digest | None = None

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        if not self.evaluation_start < self.evaluation_end <= self.outcome_as_of:
            raise ValueError("expected a nonempty evaluation period ending by outcome_as_of")
        if len(set(self.geography_ids)) != len(self.geography_ids):
            raise ValueError("duplicate geography IDs")
        return self

    def digest(self) -> str:
        return _canonical_digest(self)


class OutcomeVintage(Record):
    dataset_version: Reference
    outcome_snapshot: Reference


class OutcomePublication(OutcomeVintage):
    """Independently resolved availability of this exact outcome vintage."""

    availability_evidence: Reference
    available_at: UTCDateTime


class PanelSlot(EvaluationCase):
    exclusion_reason: Reference | None = None

    def evaluation_case(self) -> EvaluationCase:
        return EvaluationCase.model_validate(self.model_dump(exclude={"exclusion_reason"}))


class EvaluationPanel(Record):
    snapshot: Reference
    slots: Annotated[tuple[PanelSlot, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def check_unique_slots(self) -> Self:
        if len({slot.evaluation_case() for slot in self.slots}) != len(self.slots):
            raise ValueError("duplicate registered panel slots")
        return self

    def digest(self) -> str:
        slots = tuple(
            sorted(
                self.slots,
                key=lambda slot: (
                    slot.geography_id,
                    slot.origin,
                    slot.window_start,
                    slot.window_end,
                ),
            )
        )
        return _canonical_digest(EvaluationPanel(snapshot=self.snapshot, slots=slots))


class ReportRequest(Record):
    plan: ReportPlan
    outcomes: OutcomeVintage
    folds: Annotated[tuple[Fold, ...], Field(min_length=1)]
    comparisons: NoComparisons = ()
    limitations: Annotated[tuple[Reference, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def check_scope(self) -> Self:
        if len({fold.key for fold in self.folds}) != len(self.folds):
            raise ValueError("duplicate fold keys")
        geography_ids = set(self.plan.geography_ids)
        protocol = self.folds[0].protocol
        if (
            protocol.snapshot != self.plan.plan_snapshot
            or protocol.plan_sha256 != self.plan.digest()
        ):
            raise ValueError("registration does not match the immutable report plan")
        if any(fold.protocol != protocol for fold in self.folds):
            raise ValueError("conflicting protocol registrations")
        case_keys = {fold.evaluation_case() for fold in self.folds}
        if len(case_keys) != len(self.folds):
            raise ValueError("duplicate evaluation cases")

        for fold in self.folds:
            if not self.plan.evaluation_start <= fold.origin < self.plan.evaluation_end:
                raise ValueError("fold origin outside evaluation period")
            if self.plan.outcome_as_of - fold.window_end < self.plan.constraints.outcome_maturity:
                raise ValueError("fold target window has not matured by the outcome freeze")
            if (
                fold.target_version != self.plan.target_version
                or fold.horizon != self.plan.horizon
                or fold.geography_version != self.plan.geography_version
                or fold.geography_id not in geography_ids
            ):
                raise ValueError("fold target, horizon or geography differs from report plan")
        return self


EvidenceStatus = Literal["demonstration", "descriptive", "provenance_review_required", "blocked"]
PanelStatus = Literal["unverified", "incomplete", "verified"]
PublicationStatus = Literal["unverified", "verified"]


def _panel_check(
    plan: ReportPlan, panel: EvaluationPanel | None, audits: tuple[Audit, ...]
) -> tuple[PanelStatus, tuple[EvaluationCase, ...]]:
    cases = {audit.evaluation_case for audit in audits}
    if len(cases) != len(audits):
        raise ValueError("duplicate evaluation cases")
    if panel is None:
        return "unverified", ()
    if panel.snapshot != plan.panel_snapshot or panel.digest() != plan.panel_sha256:
        raise ValueError("resolved panel differs from registered panel content")
    expected: dict[EvaluationCase, str | None] = {}
    for slot in panel.slots:
        if (
            slot.geography_id not in plan.geography_ids
            or not plan.evaluation_start <= slot.origin < plan.evaluation_end
            or not plan.constraints._matches_window(slot.origin, slot.window_start, slot.window_end)
        ):
            raise ValueError("registered panel slot differs from report plan")
        expected[slot.evaluation_case()] = slot.exclusion_reason
    if cases.difference(expected):
        raise ValueError("fold contains an unregistered panel slot")
    if any(expected[case] is not None for case in cases):
        raise ValueError("fold occupies an excluded panel slot")
    missing = tuple(
        case for case, reason in expected.items() if reason is None and case not in cases
    )
    return ("incomplete" if missing else "verified"), missing


def _status(mode: EvidenceMode, audits: tuple[Audit, ...], panel: PanelStatus) -> EvidenceStatus:
    if panel == "incomplete" or any(audit.findings for audit in audits):
        return "blocked"
    if mode == "synthetic":
        return "demonstration"
    if mode == "retrospective":
        return "descriptive"
    return "provenance_review_required"


class BenchmarkReport(Record):
    schema_version: Literal[3] = 3
    report_type: Literal["historical_validation_manifest"] = "historical_validation_manifest"
    input_sha256: Digest
    evidence_mode: EvidenceMode
    evidence_status: EvidenceStatus
    plan: ReportPlan
    outcomes: OutcomeVintage
    registration: Registration
    resolved_panel: EvaluationPanel | None
    panel_status: PanelStatus
    missing_panel_slots: tuple[EvaluationCase, ...]
    outcome_publication: OutcomePublication | None
    outcome_publication_status: PublicationStatus
    audits: Annotated[tuple[Audit, ...], Field(min_length=1)]
    comparisons: NoComparisons
    limitations: tuple[Reference, ...]

    @model_validator(mode="after")
    def check_status(self) -> Self:
        if self.evidence_status != _status(self.evidence_mode, self.audits, self.panel_status):
            raise ValueError("evidence status conflicts with mode or audit findings")
        if (
            self.registration.snapshot != self.plan.plan_snapshot
            or self.registration.plan_sha256 != self.plan.digest()
        ):
            raise ValueError("registration does not match the immutable report plan")
        if self.evidence_mode != self.registration.evidence_mode:
            raise ValueError("report evidence mode differs from registered evidence mode")
        if (self.panel_status, self.missing_panel_slots) != _panel_check(
            self.plan, self.resolved_panel, self.audits
        ):
            raise ValueError("panel status conflicts with panel accounting")
        if self.outcome_publication is None:
            if self.outcome_publication_status != "unverified":
                raise ValueError("missing outcome publication evidence")
        else:
            if (
                self.outcome_publication.dataset_version != self.outcomes.dataset_version
                or self.outcome_publication.outcome_snapshot != self.outcomes.outcome_snapshot
            ):
                raise ValueError("publication evidence refers to a different outcome vintage")
            if self.outcome_publication.available_at > self.plan.outcome_as_of:
                raise ValueError("outcome vintage was unavailable at the outcome freeze")
            if self.outcome_publication_status != "verified":
                raise ValueError("outcome publication status conflicts with evidence")
        return self


def build_report(
    request: ReportRequest,
    *,
    verified_registration: Registration,
    resolved_panel: EvaluationPanel | None = None,
    verified_outcome_publication: OutcomePublication | None = None,
) -> BenchmarkReport:
    """Build a manifest using evidence obtained independently of the request.

    The caller verifies receipt and publication authenticity at their sources.
    The panel content is checked against the digest in the registered plan.
    """
    request = ReportRequest.model_validate(request)
    verified_registration = Registration.model_validate(verified_registration)
    if request.folds[0].protocol != verified_registration:
        raise ValueError("fold protocol conflicts with the verified registration")
    audits = tuple(audit_fold(fold, request.plan.constraints) for fold in request.folds)
    mode = verified_registration.evidence_mode
    if resolved_panel is not None:
        resolved_panel = EvaluationPanel.model_validate(resolved_panel)
    panel_status, missing_slots = _panel_check(request.plan, resolved_panel, audits)
    return BenchmarkReport(
        input_sha256=_canonical_digest(request),
        evidence_mode=mode,
        evidence_status=_status(mode, audits, panel_status),
        plan=request.plan,
        outcomes=request.outcomes,
        registration=verified_registration,
        resolved_panel=resolved_panel,
        panel_status=panel_status,
        missing_panel_slots=missing_slots,
        outcome_publication=verified_outcome_publication,
        outcome_publication_status="verified" if verified_outcome_publication else "unverified",
        audits=audits,
        comparisons=(),
        limitations=request.limitations,
    )
