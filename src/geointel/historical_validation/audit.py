"""Validate declared availability and split boundaries for one rolling-origin fold."""

from datetime import timedelta
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
EvidenceMode = Literal[
    "synthetic", "retrospective", "historical_replay", "historical_archive", "prospective"
]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Vintage(Record):
    snapshot: Reference
    availability_evidence: Reference
    available_at: AwareDatetime


class DevelopmentExample(Record):
    key: Reference
    role: Literal["train", "calibration"]
    origin: AwareDatetime
    window_end: AwareDatetime
    features: Annotated[tuple[Vintage, ...], Field(min_length=1)]
    label: Vintage

    @model_validator(mode="after")
    def check_window(self) -> Self:
        if self.origin >= self.window_end:
            raise ValueError("development windows must end after their origin")
        return self


class Fold(Record):
    """One frozen model or replay at a single decision cutoff."""

    key: Reference
    target_version: Reference
    geography_version: Reference
    geography_id: Reference
    horizon: Reference
    window_start: AwareDatetime
    window_end: AwareDatetime
    mode: EvidenceMode
    origin: AwareDatetime
    manifest: Reference
    embargo: Annotated[timedelta, Field(ge=timedelta(0))]
    fitted_at: AwareDatetime
    calibrated_at: AwareDatetime | None
    feature_inputs: Annotated[tuple[Vintage, ...], Field(min_length=1)]
    development: tuple[DevelopmentExample, ...]
    forecast: Vintage
    issued_at: AwareDatetime
    protocol: Vintage

    @model_validator(mode="after")
    def check_window(self) -> Self:
        if not self.origin <= self.window_start < self.window_end:
            raise ValueError("test window must be nonempty and start at or after origin")
        return self


FindingCode = Literal[
    "fit_after_origin",
    "calibration_before_fit",
    "calibration_after_origin",
    "forecast_before_model_ready",
    "availability_before_issue",
    "forecast_after_origin",
    "protocol_after_origin",
    "feature_after_cutoff",
    "duplicate_development_key",
    "calibration_step_missing",
    "calibration_examples_missing",
    "development_window_overlap",
    "label_before_window_end",
    "label_after_fit",
]


class Finding(Record):
    code: FindingCode
    reference: Reference


class Audit(Record):
    fold_key: Reference
    manifest: Reference
    findings: tuple[Finding, ...]


def audit_fold(fold: Fold) -> Audit:
    """Check a supplied manifest. Its completeness and authenticity require review."""
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
    add(fold.issued_at < ready, "forecast_before_model_ready", fold.forecast.snapshot)
    add(
        fold.forecast.available_at < fold.issued_at,
        "availability_before_issue",
        fold.forecast.snapshot,
    )
    if fold.mode in {"historical_archive", "prospective"}:
        add(
            fold.forecast.available_at > fold.origin,
            "forecast_after_origin",
            fold.forecast.snapshot,
        )
    if fold.mode == "prospective":
        add(
            fold.protocol.available_at > fold.origin,
            "protocol_after_origin",
            fold.protocol.snapshot,
        )

    for feature in fold.feature_inputs:
        add(
            feature.available_at > min(fold.origin, fold.issued_at),
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
            next_partition - example.window_end < fold.embargo,
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
        add(example.label.available_at > fit_time, "label_after_fit", example.label.snapshot)

    return Audit(fold_key=fold.key, manifest=fold.manifest, findings=tuple(findings))
