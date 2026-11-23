"""Validate declared availability and split boundaries for one rolling-origin fold."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
EvidenceMode = Literal[
    "synthetic", "retrospective", "historical_replay", "historical_archive", "prospective"
]


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UTCDateTime = Annotated[AwareDatetime, AfterValidator(_utc)]
Duration = Annotated[timedelta, Field(ge=timedelta(0))]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class Vintage(Record):
    snapshot: Reference
    availability_evidence: Reference
    available_at: UTCDateTime


class Registration(Vintage):
    """Receipt for an immutable plan, issued by an independently verified source."""

    plan_sha256: Digest


class StudyConstraints(Record):
    schema_version: Literal[1]
    forecast_lead: Duration
    window_duration: Annotated[timedelta, Field(gt=timedelta(0))]
    outcome_maturity: Duration
    embargo: Duration

    def _matches_window(self, origin: datetime, start: datetime, end: datetime) -> bool:
        return start - origin == self.forecast_lead and end - start == self.window_duration


class ReplayClock(Record):
    issued_at: UTCDateTime
    available_at: UTCDateTime


class DevelopmentExample(Record):
    key: Reference
    role: Literal["train", "calibration"]
    origin: UTCDateTime
    window_start: UTCDateTime
    window_end: UTCDateTime
    features: Annotated[tuple[Vintage, ...], Field(min_length=1)]
    label: Vintage

    @model_validator(mode="after")
    def check_window(self) -> Self:
        if not self.origin <= self.window_start < self.window_end:
            raise ValueError("development window must be nonempty and start at or after origin")
        return self


class Fold(Record):
    """One frozen model or replay at a single decision cutoff."""

    key: Reference
    target_version: Reference
    geography_version: Reference
    geography_id: Reference
    horizon: Reference
    window_start: UTCDateTime
    window_end: UTCDateTime
    mode: EvidenceMode
    origin: UTCDateTime
    manifest: Reference
    fitted_at: UTCDateTime
    calibrated_at: UTCDateTime | None
    feature_inputs: Annotated[tuple[Vintage, ...], Field(min_length=1)]
    development: tuple[DevelopmentExample, ...]
    forecast: Vintage
    issued_at: UTCDateTime
    protocol: Registration
    replay_clock: ReplayClock | None = None

    @model_validator(mode="after")
    def check_window(self) -> Self:
        if not self.origin <= self.window_start < self.window_end:
            raise ValueError("test window must be nonempty and start at or after origin")
        if (self.replay_clock is not None) != (self.mode == "historical_replay"):
            raise ValueError("historical replay requires a separate simulated forecast clock")
        return self


FindingCode = Literal[
    "fit_after_origin",
    "calibration_before_fit",
    "calibration_after_origin",
    "forecast_before_model_ready",
    "availability_before_issue",
    "forecast_after_origin",
    "replay_publication_before_simulated_availability",
    "protocol_after_origin",
    "feature_after_cutoff",
    "duplicate_development_key",
    "calibration_step_missing",
    "calibration_examples_missing",
    "development_window_overlap",
    "label_before_window_end",
    "label_after_fit",
    "label_before_maturity",
    "study_window_mismatch",
]


class Finding(Record):
    code: FindingCode
    reference: Reference


class Audit(Record):
    fold_key: Reference
    manifest: Reference
    findings: tuple[Finding, ...]


def audit_fold(fold: Fold, constraints: StudyConstraints) -> Audit:
    """Check a supplied manifest. Its completeness and authenticity require review."""
    fold = Fold.model_validate(fold)
    constraints = StudyConstraints.model_validate(constraints)
    findings: list[Finding] = []

    def add(condition: bool, code: FindingCode, reference: str) -> None:
        if condition:
            findings.append(Finding(code=code, reference=reference))

    ready = fold.calibrated_at or fold.fitted_at
    add(fold.fitted_at > fold.origin, "fit_after_origin", fold.key)
    add(ready < fold.fitted_at, "calibration_before_fit", fold.key)
    add(
        ready > fold.origin and fold.calibrated_at is not None, "calibration_after_origin", fold.key
    )
    decision_issue = fold.issued_at
    decision_availability = fold.forecast.available_at
    if fold.replay_clock:
        decision_issue = fold.replay_clock.issued_at
        decision_availability = fold.replay_clock.available_at
        add(
            decision_availability < decision_issue,
            "availability_before_issue",
            fold.forecast.snapshot,
        )
        add(
            fold.issued_at < decision_availability,
            "replay_publication_before_simulated_availability",
            fold.forecast.snapshot,
        )
    add(decision_issue < ready, "forecast_before_model_ready", fold.forecast.snapshot)
    add(
        fold.forecast.available_at < fold.issued_at,
        "availability_before_issue",
        fold.forecast.snapshot,
    )
    if fold.mode != "retrospective":
        add(
            decision_availability > fold.origin,
            "forecast_after_origin",
            fold.forecast.snapshot,
        )
    first_decision = min(
        fold.origin,
        decision_issue,
        fold.fitted_at,
        ready,
        *(example.origin for example in fold.development),
    )
    add(
        fold.protocol.available_at >= first_decision,
        "protocol_after_origin",
        fold.protocol.snapshot,
    )
    add(
        not constraints._matches_window(fold.origin, fold.window_start, fold.window_end),
        "study_window_mismatch",
        fold.key,
    )

    for feature in fold.feature_inputs:
        add(
            feature.available_at > min(fold.origin, decision_issue),
            "feature_after_cutoff",
            feature.snapshot,
        )

    add(
        fold.calibrated_at is not None
        and not any(example.role == "calibration" for example in fold.development),
        "calibration_examples_missing",
        fold.key,
    )
    calibration_start = min(
        (example.origin for example in fold.development if example.role == "calibration"),
        default=fold.origin,
    )
    keys: set[str] = set()
    for example in fold.development:
        add(example.key in keys, "duplicate_development_key", example.key)
        keys.add(example.key)
        add(
            not constraints._matches_window(
                example.origin, example.window_start, example.window_end
            ),
            "study_window_mismatch",
            example.key,
        )
        fit_time = fold.fitted_at
        next_partition = min(calibration_start, fold.origin)
        if example.role == "calibration":
            add(fold.calibrated_at is None, "calibration_step_missing", example.key)
            fit_time = ready
            next_partition = fold.origin
            add(
                example.origin < fold.fitted_at,
                "development_window_overlap",
                example.key,
            )
        add(
            next_partition - example.window_end < constraints.embargo,
            "development_window_overlap",
            example.key,
        )
        for feature in example.features:
            add(
                feature.available_at > example.origin,
                "feature_after_cutoff",
                feature.snapshot,
            )
        add(
            example.label.available_at < example.window_end,
            "label_before_window_end",
            example.label.snapshot,
        )
        add(
            example.window_end <= example.label.available_at
            and example.label.available_at - example.window_end < constraints.outcome_maturity,
            "label_before_maturity",
            example.label.snapshot,
        )
        add(example.label.available_at > fit_time, "label_after_fit", example.label.snapshot)

    return Audit(fold_key=fold.key, manifest=fold.manifest, findings=tuple(findings))
