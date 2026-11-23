"""Versioned historical validation manifests with content-bound registration."""

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from geointel.historical_validation.audit import (
    Audit,
    Digest,
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
        if len({fold.mode for fold in self.folds}) != 1:
            raise ValueError("a report requires a single evidence mode")
        geography_ids = set(self.plan.geography_ids)
        protocol = self.folds[0].protocol
        if (
            protocol.snapshot != self.plan.plan_snapshot
            or protocol.plan_sha256 != self.plan.digest()
        ):
            raise ValueError("registration does not match the immutable report plan")
        if any(fold.protocol != protocol for fold in self.folds):
            raise ValueError("conflicting protocol registrations")
        case_keys = {
            (fold.geography_id, fold.origin, fold.window_start, fold.window_end)
            for fold in self.folds
        }
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


def _status(mode: EvidenceMode, audits: tuple[Audit, ...]) -> EvidenceStatus:
    if any(audit.findings for audit in audits):
        return "blocked"
    if mode == "synthetic":
        return "demonstration"
    if mode == "retrospective":
        return "descriptive"
    return "provenance_review_required"


class BenchmarkReport(Record):
    schema_version: Literal[2] = 2
    report_type: Literal["historical_validation_manifest"] = "historical_validation_manifest"
    input_sha256: Digest
    evidence_mode: Literal[
        "synthetic", "retrospective", "historical_replay", "historical_archive", "prospective"
    ]
    evidence_status: Literal[
        "demonstration", "descriptive", "provenance_review_required", "blocked"
    ]
    plan: ReportPlan
    outcomes: OutcomeVintage
    registration: Registration
    audits: Annotated[tuple[Audit, ...], Field(min_length=1)]
    comparisons: NoComparisons
    limitations: tuple[Reference, ...]

    @model_validator(mode="after")
    def check_status(self) -> Self:
        if self.evidence_status != _status(self.evidence_mode, self.audits):
            raise ValueError("evidence status conflicts with mode or audit findings")
        if (
            self.registration.snapshot != self.plan.plan_snapshot
            or self.registration.plan_sha256 != self.plan.digest()
        ):
            raise ValueError("registration does not match the immutable report plan")
        return self


def build_report(request: ReportRequest, *, verified_registration: Registration) -> BenchmarkReport:
    """Build a manifest using a receipt independently verified against the registry.

    The caller must obtain this receipt independently of the request. This function
    checks the content binding and receipt consistency, not registry authenticity.
    """
    request = ReportRequest.model_validate(request)
    verified_registration = Registration.model_validate(verified_registration)
    if request.folds[0].protocol != verified_registration:
        raise ValueError("fold protocol conflicts with the verified registration")
    audits = tuple(audit_fold(fold, request.plan.constraints) for fold in request.folds)
    mode = request.folds[0].mode
    status = _status(mode, audits)
    return BenchmarkReport(
        input_sha256=_canonical_digest(request),
        evidence_mode=mode,
        evidence_status=status,
        plan=request.plan,
        outcomes=request.outcomes,
        registration=verified_registration,
        audits=audits,
        comparisons=(),
        limitations=request.limitations,
    )
