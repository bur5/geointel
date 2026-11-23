"""Versioned metadata accompanying an immutable scoring artifact."""

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from geointel.historical_validation.audit import (
    Audit,
    EvidenceMode,
    Fold,
    Record,
    Reference,
    audit_fold,
)

Count = Annotated[int, Field(strict=True, ge=0)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ReportPlan(Record):
    plan_snapshot: Reference
    implementation_revision: Reference
    target_version: Reference
    outcome_definition: Reference
    geography_version: Reference
    geography_ids: Annotated[tuple[Reference, ...], Field(min_length=1)]
    horizon: Reference
    evaluation_start: AwareDatetime
    evaluation_end: AwareDatetime
    outcome_as_of: AwareDatetime
    dataset_version: Reference
    outcome_snapshot: Reference
    panel_snapshot: Reference

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        if not self.evaluation_start < self.evaluation_end <= self.outcome_as_of:
            raise ValueError("expected a nonempty evaluation period ending by outcome_as_of")
        if len(set(self.geography_ids)) != len(self.geography_ids):
            raise ValueError("duplicate geography IDs")
        return self


class Sample(Record):
    eligible_slots: Count
    scored: Count
    events: Count
    # Counts must be mutually exclusive; use the predeclared exclusion priority.
    exclusions: dict[Reference, Count]

    @model_validator(mode="after")
    def check_totals(self) -> Self:
        if self.events > self.scored:
            raise ValueError("events exceed scored rows")
        if self.scored + sum(self.exclusions.values()) != self.eligible_slots:
            raise ValueError("sample counts do not reconcile")
        return self


class Comparison(Record):
    model: Reference
    version: Reference
    forecast_snapshot: Reference
    baseline: Reference
    baseline_version: Reference
    baseline_snapshot: Reference
    matched_keys: Digest
    sample: Sample
    metrics_artifact: Reference
    calibration_artifact: Reference | None
    uncertainty_artifact: Reference | None


class ReportRequest(Record):
    plan: ReportPlan
    folds: Annotated[tuple[Fold, ...], Field(min_length=1)]
    comparisons: tuple[Comparison, ...] = ()
    limitations: Annotated[tuple[Reference, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def check_scope(self) -> Self:
        if len({fold.key for fold in self.folds}) != len(self.folds):
            raise ValueError("duplicate fold keys")
        if len({fold.mode for fold in self.folds}) != 1:
            raise ValueError("a report requires a single evidence mode")
        geography_ids = set(self.plan.geography_ids)
        for fold in self.folds:
            if not self.plan.evaluation_start <= fold.origin < self.plan.evaluation_end:
                raise ValueError("fold origin outside evaluation period")
            if fold.window_end > self.plan.outcome_as_of:
                raise ValueError("fold target window ends after the outcome freeze")
            if (
                fold.target_version != self.plan.target_version
                or fold.horizon != self.plan.horizon
                or fold.geography_version != self.plan.geography_version
                or fold.geography_id not in geography_ids
            ):
                raise ValueError("fold target, horizon or geography differs from report plan")
            if fold.protocol.snapshot != self.plan.plan_snapshot:
                raise ValueError("fold protocol differs from report plan")
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
    schema_version: Literal[1] = 1
    report_type: Literal["historical_validation_manifest"] = "historical_validation_manifest"
    input_sha256: Digest
    evidence_mode: Literal[
        "synthetic", "retrospective", "historical_replay", "historical_archive", "prospective"
    ]
    evidence_status: Literal[
        "demonstration", "descriptive", "provenance_review_required", "blocked"
    ]
    plan: ReportPlan
    audits: Annotated[tuple[Audit, ...], Field(min_length=1)]
    comparisons: tuple[Comparison, ...]
    limitations: tuple[Reference, ...]

    @model_validator(mode="after")
    def check_status(self) -> Self:
        if self.evidence_status != _status(self.evidence_mode, self.audits):
            raise ValueError("evidence status conflicts with mode or audit findings")
        if self.evidence_status == "blocked" and self.comparisons:
            raise ValueError("blocked reports cannot attach comparisons")
        return self


def build_report(request: ReportRequest) -> BenchmarkReport:
    """Generate a manifest. An audit pass only checks the supplied metadata."""
    audits = tuple(audit_fold(fold) for fold in request.folds)
    mode = request.folds[0].mode
    status = _status(mode, audits)
    canonical = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return BenchmarkReport(
        input_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        evidence_mode=mode,
        evidence_status=status,
        plan=request.plan,
        audits=audits,
        comparisons=() if status == "blocked" else request.comparisons,
        limitations=request.limitations,
    )
