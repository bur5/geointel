import json
from datetime import UTC, datetime, timedelta
from importlib.resources import files

from geointel.connectors.base import DisabledConnector
from geointel.domain.schemas import (
    NormalizedEvidence,
    NormalizedForecastSignal,
    NormalizedOperationalEvent,
)
from geointel.validation.domain import ValidationCase, ValidationSuite

FIXED_TIME = datetime(2025, 1, 15, 12, tzinfo=UTC)
_ALLOWED_SUITE = "five-country-v1"


def load_suite(suite_id: str = _ALLOWED_SUITE) -> ValidationSuite:
    if suite_id != _ALLOWED_SUITE:
        raise ValueError(f"unknown validation suite: {suite_id}")
    path = files("geointel.validation.fixtures").joinpath(f"{suite_id}.json")
    raw = path.read_text(encoding="utf-8")
    if len(raw.encode()) > 100_000:
        raise ValueError("validation fixture exceeds 100 KB")
    return ValidationSuite.model_validate(json.loads(raw))


class FailedFixtureConnector:
    def __init__(self, name: str):
        self.connector_name = name

    def collect(self, location: str, horizon_months: int):
        raise RuntimeError("synthetic provider outage")


class FixtureConnector:
    def __init__(self, name: str, case: ValidationCase, status: str):
        self.connector_name, self.case, self.status = name, case, status

    def collect(self, location: str, horizon_months: int):
        provenance = {"synthetic_fixture": True, "suite": _ALLOWED_SUITE, "case": self.case.case_id}
        mismatch = self.status == "mismatched"
        stale = self.status == "stale"
        notes = (["geographic mismatch: synthetic subnational record"] if mismatch else []) + (
            ["stale event: outside requested operational window"] if stale else []
        )
        if self.connector_name == "UCDP":
            return [
                NormalizedEvidence(
                    source_name="UCDP",
                    source_record_id=f"{self.case.case_id}-history",
                    title="Synthetic historical artifact",
                    summary="Synthetic historical context; not a real-world claim.",
                    event_date=FIXED_TIME - timedelta(days=800 if stale else 200),
                    retrieved_at=FIXED_TIME,
                    geographic_scope=location,
                    provenance={**provenance, "temporal_status": self.status},
                )
            ]
        if self.connector_name == "ACLED":
            count = 40 if self.case.scenario == "high_volume" else 1
            records = [
                NormalizedOperationalEvent(
                    source_record_id=f"{self.case.case_id}-event-{i}",
                    event_date=FIXED_TIME - timedelta(days=i),
                    event_type="Synthetic test event",
                    country=location,
                    admin1="Synthetic Region" if mismatch else None,
                    fatalities=None if i == 0 else 0,
                    notes="Synthetic report; not independently verified.",
                    retrieved_at=FIXED_TIME,
                    alignment_status="mismatched" if mismatch else "aligned",
                    alignment_notes=notes,
                    provenance={**provenance, "fatalities_uncertain": i == 0},
                )
                for i in range(count)
            ]
            if count > 1:
                records.append(records[0].model_copy())  # exact provider duplicate
            return records
        prediction = 0.8 if self.connector_name == "VIEWS" else 0.2
        return [
            NormalizedForecastSignal(
                provider=self.connector_name,
                source_record_id=f"{self.case.case_id}-{self.connector_name.lower()}",
                model_name="synthetic-validation-model",
                geographic_unit="country",
                location=location,
                issue_date=FIXED_TIME,
                target_start=FIXED_TIME,
                target_end=FIXED_TIME + timedelta(days=365),
                horizon_months=12,
                target_variable="synthetic organized violence indicator",
                prediction=prediction,
                unit="provider_native_index",
                retrieved_at=FIXED_TIME,
                alignment_status="aligned",
                provenance={**provenance, "predictive_not_observed": True},
            )
        ]


def connectors_for(case: ValidationCase):
    result = []
    for name in ("UCDP", "ACLED", "VIEWS", "CAST"):
        status = case.sources[name]
        if status == "missing":
            result.append(DisabledConnector(name))
        elif status == "failed":
            result.append(FailedFixtureConnector(name))
        else:
            result.append(FixtureConnector(name, case, status))
    return result
