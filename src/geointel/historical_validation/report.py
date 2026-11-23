"""Versioned historical validation manifests with content-bound registration."""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from itertools import chain
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
    SnapshotEvidence,
    StudyConstraints,
    UTCDateTime,
    audit_fold,
    snapshot_inventory,
)

# The historical panel adapter is required before any scored attachment is supported.
NoComparisons = Annotated[tuple[object, ...], Field(max_length=0)]


def _canonical_digest(record: Record) -> str:
    def omit_legacy_defaults(fields: dict[str, object]) -> dict[str, object]:
        # Before snapshot metadata supported versions, an unknown version was absent.
        if "dataset_version" in fields and fields["dataset_version"] is None:
            del fields["dataset_version"]
        return fields

    data = json.loads(record.model_dump_json(), object_hook=omit_legacy_defaults)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
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

    def snapshot_declaration(self) -> SnapshotEvidence:
        return SnapshotEvidence(
            snapshot=self.outcome_snapshot,
            dataset_version=self.dataset_version,
            availability_evidence=self.availability_evidence,
            available_at=self.available_at,
        )


class PanelSlot(EvaluationCase):
    exclusion_reason: Reference | None = None

    def evaluation_case(self) -> EvaluationCase:
        return EvaluationCase.model_validate(self.model_dump(exclude={"exclusion_reason"}))


def _case_order(case: EvaluationCase) -> tuple[str, datetime, datetime, datetime]:
    return case.geography_id, case.origin, case.window_start, case.window_end


class EvaluationPanel(Record):
    snapshot: Reference
    slots: Annotated[tuple[PanelSlot, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def check_unique_slots(self) -> Self:
        if len({slot.evaluation_case() for slot in self.slots}) != len(self.slots):
            raise ValueError("duplicate registered panel slots")
        return self

    def digest(self) -> str:
        return _canonical_digest(self.canonical())

    def canonical(self) -> "EvaluationPanel":
        return EvaluationPanel(
            snapshot=self.snapshot, slots=tuple(sorted(self.slots, key=_case_order))
        )


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
        _check_outcome_version(self.outcomes, snapshot_inventory(self.snapshot_declarations()))
        return self

    def snapshot_declarations(self) -> Iterator[SnapshotEvidence]:
        for fold in self.folds:
            yield from fold.snapshot_declarations()


EvidenceStatus = Literal["demonstration", "descriptive", "provenance_review_required", "blocked"]
PanelStatus = Literal["unverified", "incomplete", "verified"]
PublicationStatus = Literal["unverified", "verified"]


def _panel_check(
    plan: ReportPlan, panel: EvaluationPanel | None, audits: tuple[Audit, ...]
) -> tuple[Literal["unverified", "incomplete", "complete"], tuple[EvaluationCase, ...]]:
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
    return ("incomplete" if missing else "complete"), missing


def _status(mode: EvidenceMode, audits: tuple[Audit, ...], *, incomplete: bool) -> EvidenceStatus:
    if incomplete or any(audit.findings for audit in audits):
        return "blocked"
    if mode == "synthetic":
        return "demonstration"
    if mode == "retrospective":
        return "descriptive"
    return "provenance_review_required"


class BenchmarkReport(Record):
    schema_version: Literal[3, 4] = 4
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
        if self.evidence_status != _status(
            self.evidence_mode, self.audits, incomplete=self.panel_status == "incomplete"
        ):
            raise ValueError("evidence status conflicts with mode or audit findings")
        if (
            self.registration.snapshot != self.plan.plan_snapshot
            or self.registration.plan_sha256 != self.plan.digest()
        ):
            raise ValueError("registration does not match the immutable report plan")
        if self.evidence_mode != self.registration.evidence_mode:
            raise ValueError("report evidence mode differs from registered evidence mode")
        coverage, missing = _panel_check(self.plan, self.resolved_panel, self.audits)
        structural_panel = "incomplete" if coverage == "incomplete" else "unverified"
        panel_claims = {structural_panel}
        if self.schema_version == 3 and coverage == "complete":
            panel_claims.add("verified")
        if self.panel_status not in panel_claims or self.missing_panel_slots != missing:
            raise ValueError("panel status conflicts with panel accounting")
        if self.outcome_publication is not None:
            _check_publication(self.plan, self.outcomes, self.outcome_publication)
        if self.outcome_publication_status == "verified":
            if self.outcome_publication is None:
                raise ValueError("missing outcome publication evidence")
            if self.schema_version != 3:
                raise ValueError("publication verification requires external evidence")
        # Legacy wire claims carry no authority, including when loaded from a model instance.
        object.__setattr__(self, "panel_status", structural_panel)
        object.__setattr__(self, "outcome_publication_status", "unverified")
        return self


def _check_publication(
    plan: ReportPlan, outcomes: OutcomeVintage, publication: OutcomePublication
) -> None:
    if (
        publication.dataset_version != outcomes.dataset_version
        or publication.outcome_snapshot != outcomes.outcome_snapshot
    ):
        raise ValueError("publication evidence refers to a different outcome vintage")
    if publication.available_at > plan.outcome_as_of:
        raise ValueError("outcome vintage was unavailable at the outcome freeze")


def _check_outcome_version(
    outcomes: OutcomeVintage, inventory: dict[str, SnapshotEvidence]
) -> None:
    snapshot = inventory.get(outcomes.outcome_snapshot)
    if snapshot is not None and snapshot.dataset_version not in (None, outcomes.dataset_version):
        raise ValueError(f"conflicting snapshot declarations for {snapshot.snapshot!r}")


def build_report(
    request: ReportRequest,
    *,
    verified_registration: Registration,
    resolved_panel: EvaluationPanel | None = None,
    verified_outcome_publication: OutcomePublication | None = None,
) -> BenchmarkReport:
    """Build a structural manifest using resolver-supplied receipt, panel and publication.

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
    if verified_outcome_publication is not None:
        verified_outcome_publication = OutcomePublication.model_validate(
            verified_outcome_publication
        )
        _check_publication(request.plan, request.outcomes, verified_outcome_publication)
    published = (
        (verified_outcome_publication.snapshot_declaration(),)
        if verified_outcome_publication is not None
        else ()
    )
    _check_outcome_version(
        request.outcomes, snapshot_inventory(chain(request.snapshot_declarations(), published))
    )
    if resolved_panel is not None:
        resolved_panel = resolved_panel.canonical()
    panel_status, missing_slots = _panel_check(request.plan, resolved_panel, audits)
    return BenchmarkReport(
        input_sha256=_canonical_digest(request),
        evidence_mode=mode,
        evidence_status=_status(mode, audits, incomplete=panel_status == "incomplete"),
        plan=request.plan,
        outcomes=request.outcomes,
        registration=verified_registration,
        resolved_panel=resolved_panel,
        panel_status="incomplete" if panel_status == "incomplete" else "unverified",
        missing_panel_slots=missing_slots,
        outcome_publication=verified_outcome_publication,
        outcome_publication_status="unverified",
        audits=audits,
        comparisons=(),
        limitations=request.limitations,
    )


@dataclass(frozen=True, slots=True)
class VerifiedReport:
    """Verification result for exact normalized report content."""

    report_sha256: str
    panel_status: Literal["incomplete", "verified"]
    outcome_publication_status: Literal["verified"] = field(default="verified", init=False)

    def matches(self, report: BenchmarkReport) -> bool:
        """Check whether this result applies to the supplied manifest."""
        try:
            return self.report_sha256 == _report_digest(BenchmarkReport.model_validate(report))
        except ValueError:
            return False


def _report_digest(report: BenchmarkReport) -> str:
    panel = report.resolved_panel
    canonical = report.model_copy(
        update={
            "resolved_panel": panel.canonical() if panel is not None else None,
            "missing_panel_slots": tuple(sorted(report.missing_panel_slots, key=_case_order)),
        }
    )
    return _canonical_digest(canonical)


def verify_report_v1(
    report: BenchmarkReport,
    *,
    original_request: ReportRequest,
    registration: Registration,
    required_panel: EvaluationPanel,
    evidence_mode: EvidenceMode,
    outcome_publication: OutcomePublication,
    source_snapshots: tuple[SnapshotEvidence, ...],
) -> VerifiedReport:
    """Recompute and compare using records independently authenticated by the caller."""
    report = BenchmarkReport.model_validate(report)
    request = ReportRequest.model_validate(original_request)
    registration = Registration.model_validate(registration)
    publication = OutcomePublication.model_validate(outcome_publication)
    panel = EvaluationPanel.model_validate(required_panel)
    if registration.evidence_mode != evidence_mode:
        raise ValueError("trusted evidence mode differs from the registration")
    expected = build_report(
        request,
        verified_registration=registration,
        resolved_panel=panel,
        verified_outcome_publication=publication,
    )
    if report.audits != expected.audits:
        raise ValueError("report audits differ from those recomputed from the original request")
    expected_sources = snapshot_inventory(
        chain(request.snapshot_declarations(), (publication.snapshot_declaration(),))
    )
    resolved_sources = snapshot_inventory(
        SnapshotEvidence.model_validate(source) for source in source_snapshots
    )
    if any(resolved_sources.get(key) != value for key, value in expected_sources.items()):
        raise ValueError(
            "source snapshot evidence differs from the original request or publication"
        )
    digest = _report_digest(report)
    if digest != _report_digest(
        expected.model_copy(update={"schema_version": report.schema_version})
    ):
        raise ValueError("report content differs from the manifest rebuilt from trusted evidence")
    return VerifiedReport(
        report_sha256=digest,
        panel_status="incomplete" if expected.missing_panel_slots else "verified",
    )
