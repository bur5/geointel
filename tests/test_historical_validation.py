import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from geointel.historical_validation.audit import Fold, Registration, StudyConstraints, audit_fold
from geointel.historical_validation.report import (
    BenchmarkReport,
    ReportPlan,
    ReportRequest,
    build_report,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def payload():
    return json.loads((FIXTURES / "synthetic_benchmark_request.json").read_text())


def registration():
    return Registration.model_validate_json(
        (FIXTURES / "synthetic_benchmark_registration.json").read_bytes()
    )


def render(payload, receipt=None):
    return build_report(
        ReportRequest.model_validate(payload),
        verified_registration=receipt if receipt is not None else registration(),
    )


def register_synthetic_plan(payload):
    protocol = dict(payload["folds"][0]["protocol"])
    protocol["plan_sha256"] = ReportPlan.model_validate(payload["plan"]).digest()
    for fold in payload["folds"]:
        fold["protocol"] = protocol.copy()
    return Registration.model_validate(protocol)


def test_synthetic_report_round_trip(payload):
    request = ReportRequest.model_validate(payload)
    report = build_report(request, verified_registration=registration())
    assert report.evidence_mode == "synthetic"
    assert report.evidence_status == "demonstration"
    assert not report.audits[0].findings
    assert (
        report.model_dump_json()
        == build_report(request, verified_registration=registration()).model_dump_json()
    )
    assert BenchmarkReport.model_validate_json(report.model_dump_json()) == report
    assert "evidence_status" in BenchmarkReport.model_json_schema()["properties"]


@pytest.mark.parametrize(
    ("field", "index", "timestamp", "finding"),
    [
        ("features", 0, "2000-01-02T00:00:00.000001Z", "feature_after_cutoff"),
        ("label", 0, "2000-01-05T00:00:00.000001Z", "label_after_fit"),
        ("label", 1, "2000-01-07T23:59:59Z", "label_before_window_end"),
        ("label", 1, "2000-01-08T23:59:59.999999Z", "label_before_maturity"),
    ],
)
def test_revision_and_label_boundaries(payload, field, index, timestamp, finding):
    vintage = payload["folds"][0]["development"][index][field]
    if field == "features":
        vintage = vintage[0]
    vintage["available_at"] = timestamp
    report = render(payload)
    assert report.evidence_status == "blocked"
    assert finding in {record.code for record in report.audits[0].findings}


def test_embargo_rejects_gap_even_with_mature_label(payload):
    payload["plan"]["constraints"]["embargo"] = "P2DT1S"
    report = render(payload, register_synthetic_plan(payload))
    assert [finding.code for finding in report.audits[0].findings] == [
        "development_window_overlap",
        "development_window_overlap",
    ]


@pytest.mark.parametrize(
    ("mode", "status"),
    [
        ("retrospective", "descriptive"),
        ("synthetic", "blocked"),
        ("historical_replay", "provenance_review_required"),
        ("historical_archive", "blocked"),
        ("prospective", "blocked"),
    ],
)
def test_later_forecast_keeps_evidence_mode(payload, mode, status):
    fold = payload["folds"][0]
    fold["mode"] = mode
    fold["issued_at"] = fold["forecast"]["available_at"] = "2001-01-10T00:00:00Z"
    if mode == "historical_replay":
        fold["replay_clock"] = {"issued_at": fold["origin"], "available_at": fold["origin"]}
    report = render(payload)
    assert report.evidence_mode == mode
    assert report.evidence_status == status


@pytest.mark.parametrize(
    "mode", ["synthetic", "retrospective", "historical_archive", "prospective"]
)
def test_protocol_must_precede_first_development_decision(payload, mode):
    fold = payload["folds"][0]
    fold["mode"] = mode
    fold["protocol"]["available_at"] = fold["development"][0]["origin"]
    report = render(payload, Registration.model_validate(fold["protocol"]))
    assert report.evidence_status == "blocked"
    assert report.audits[0].findings[0].code == "protocol_after_origin"


@pytest.mark.parametrize("field", ["availability_evidence", "available_at", "snapshot"])
def test_missing_vintage_provenance_is_invalid(payload, field):
    del payload["folds"][0]["feature_inputs"][0][field]
    with pytest.raises(ValidationError, match=field):
        ReportRequest.model_validate(payload)


@pytest.mark.parametrize("field", ["target_version", "horizon", "geography_id"])
def test_incompatible_fold_is_rejected(payload, field):
    payload["folds"][0][field] = "incompatible"
    with pytest.raises(ValidationError, match="differs from report plan"):
        ReportRequest.model_validate(payload)


def test_mixed_evidence_modes_are_rejected(payload):
    payload["folds"].append(dict(payload["folds"][0], key="second", mode="retrospective"))
    with pytest.raises(ValidationError, match="single evidence mode"):
        ReportRequest.model_validate(payload)


@pytest.mark.parametrize(
    "attachment",
    [
        {"baseline_snapshot": "unverified", "metrics_artifact": "opaque"},
        {"model_cases": ["case-1", "case-1"], "baseline_cases": ["case-1"]},
        {"model_cases": ["case-1"], "baseline_cases": ["case-2"]},
        {"outcome_snapshot": "different-vintage", "metrics": {"brier": 0}},
        {"panel": [{"outcome_status": "incomplete"}], "comparison": {"case_indices": [0]}},
    ],
    ids=["opaque-baseline", "duplicate", "disjoint", "other-vintage", "pr34-report"],
)
def test_unverified_comparisons_are_rejected_at_both_boundaries(payload, attachment):
    report = render(payload).model_dump()
    for schema, contents in [(ReportRequest, payload), (BenchmarkReport, report)]:
        contents["comparisons"] = [attachment]
        with pytest.raises(ValidationError, match="comparisons"):
            schema.model_validate(contents)


def add_second_fold(payload):
    second = deepcopy(payload["folds"][0])
    second["key"] = "second"
    second["geography_id"] = "SECOND"
    payload["plan"]["geography_ids"].append("SECOND")
    payload["folds"].append(second)
    return second


def test_one_failed_fold_blocks_report(payload):
    second = add_second_fold(payload)
    second["feature_inputs"][0]["available_at"] = "2000-01-10T00:00:01Z"
    report = render(payload, register_synthetic_plan(payload))
    assert report.evidence_status == "blocked"
    assert not report.comparisons
    assert not report.audits[0].findings
    assert report.audits[1].findings[0].code == "feature_after_cutoff"


def test_duplicate_case_keys_use_utc_instant(payload):
    second = deepcopy(payload["folds"][0])
    second["key"] = "different-id"
    second["origin"] = second["window_start"] = "2000-01-09T19:00:00-05:00"
    payload["folds"].append(second)
    with pytest.raises(ValidationError, match="duplicate evaluation cases"):
        render(payload)


@pytest.mark.parametrize(
    "field", ["available_at", "availability_evidence", "plan_sha256", "snapshot"]
)
def test_conflicting_protocol_vintages(payload, field):
    second = add_second_fold(payload)
    receipt = register_synthetic_plan(payload)
    second["protocol"][field] = {
        "available_at": "1999-01-01T00:00:00Z",
        "availability_evidence": "another-receipt",
        "plan_sha256": "0" * 64,
        "snapshot": "another-revision",
    }[field]
    with pytest.raises(ValidationError, match="conflicting protocol"):
        render(payload, receipt)


def test_revised_artifact_cannot_reuse_registration_availability(payload):
    payload["plan"]["implementation_revision"] = "new-implementation"
    with pytest.raises(ValidationError, match="immutable report plan"):
        render(payload)
    register_synthetic_plan(payload)  # Recomputing the digest cannot authenticate the old time.
    with pytest.raises(ValueError, match="verified registration"):
        render(payload)


def test_distinct_outcome_vintages_produce_distinct_manifest_hashes(payload):
    original = render(payload)
    payload["outcomes"]["outcome_snapshot"] = "revised-outcome-vintage"
    revised = render(payload)
    assert revised.registration == original.registration
    assert revised.outcomes != original.outcomes
    assert revised.input_sha256 != original.input_sha256
    assert not revised.comparisons


@pytest.mark.parametrize(
    ("field", "value"),
    [("window_start", "2000-01-10T01:00:00Z"), ("window_end", "2000-01-12T00:00:01Z")],
)
def test_fold_must_follow_registered_window(payload, field, value):
    payload["folds"][0][field] = value
    report = render(payload)
    assert report.evidence_status == "blocked"
    assert {finding.code for finding in report.audits[0].findings} == {"study_window_mismatch"}


@pytest.mark.parametrize(
    ("freeze", "accepted"),
    [
        ("2000-01-13T00:00:00Z", True),
        ("2000-01-12T23:59:59.999999Z", False),
    ],
)
def test_outcome_maturity_at_freeze(payload, freeze, accepted):
    payload["plan"]["evaluation_end"] = "2000-01-11T00:00:00Z"
    payload["plan"]["outcome_as_of"] = freeze
    receipt = register_synthetic_plan(payload)
    if accepted:
        assert render(payload, receipt).evidence_status == "demonstration"
    else:
        with pytest.raises(ValidationError, match="has not matured"):
            render(payload, receipt)


def test_offset_aliases_have_identical_report_hash(payload):
    original = render(payload)
    payload["plan"]["evaluation_start"] = "2000-01-09T19:00:00-05:00"
    payload["folds"][0]["origin"] = "2000-01-10T01:00:00+01:00"
    assert render(payload).model_dump_json() == original.model_dump_json()


@pytest.mark.parametrize(
    ("late_field", "finding"),
    [
        ("forecast", "forecast_after_origin"),
        ("feature", "feature_after_cutoff"),
        ("label", "label_after_fit"),
    ],
)
def test_zoneinfo_repeated_hour_is_chronologically_ordered(payload, late_field, finding):
    zone = ZoneInfo("America/New_York")
    early = datetime(2024, 11, 3, 1, 30, tzinfo=zone, fold=0)
    late = early.replace(fold=1)
    fold = payload["folds"][0]
    constraints = StudyConstraints.model_validate(payload["plan"]["constraints"])
    if late_field == "label":
        fold["fitted_at"] = early
        fold["development"][0]["label"]["available_at"] = late
    else:
        fold["issued_at"] = fold["origin"] = fold["window_start"] = early
        fold["window_end"] = early.astimezone(UTC) + timedelta(days=2)
        target = fold["forecast"] if late_field == "forecast" else fold["feature_inputs"][0]
        target["available_at"] = late
    validated = Fold.model_validate(fold)
    assert finding in {item.code for item in audit_fold(validated, constraints).findings}


@pytest.mark.parametrize(("month", "day", "blocked"), [(3, 10, True), (11, 3, False)])
def test_embargo_uses_elapsed_time_across_dst(payload, month, day, blocked):
    zone = ZoneInfo("America/New_York")
    origin = datetime(2024, month, day, 12, tzinfo=zone)
    previous = origin - timedelta(days=1)
    fold = payload["folds"][0]
    fold["origin"] = fold["window_start"] = fold["issued_at"] = origin
    fold["window_end"] = origin.astimezone(UTC) + timedelta(days=2)
    fold["forecast"]["available_at"] = origin
    fold["calibrated_at"] = None
    fold["fitted_at"] = previous
    train = fold["development"][0]
    train["window_end"] = train["label"]["available_at"] = previous
    train["origin"] = train["window_start"] = previous.astimezone(UTC) - timedelta(days=2)
    fold["development"] = [train]
    constraints = StudyConstraints.model_validate(
        dict(payload["plan"]["constraints"], outcome_maturity="PT0S")
    )
    findings = audit_fold(Fold.model_validate(fold), constraints).findings
    assert [item.code for item in findings] == (["development_window_overlap"] if blocked else [])


def test_replay_late_on_simulated_clock_blocks_comparison_eligibility(payload):
    fold = payload["folds"][0]
    fold["mode"] = "historical_replay"
    fold["issued_at"] = fold["forecast"]["available_at"] = "2001-01-10T00:00:00Z"
    fold["replay_clock"] = {
        "issued_at": fold["origin"],
        "available_at": "2000-01-10T00:00:01Z",
    }
    report = render(payload)
    assert report.evidence_status == "blocked"
    assert report.audits[0].findings[0].code == "forecast_after_origin"


def test_inconsistent_evidence_status_is_rejected(payload):
    report = render(payload).model_dump()
    report["evidence_status"] = "provenance_review_required"
    with pytest.raises(ValidationError, match="evidence status conflicts"):
        BenchmarkReport.model_validate(report)


def test_repeated_local_origins_are_distinct_cases_and_hashes(payload):
    zone = ZoneInfo("America/New_York")
    early = datetime(2024, 11, 3, 1, 30, tzinfo=zone, fold=0)
    late = early.replace(fold=1)
    payload["plan"].update(
        evaluation_start="2024-11-03T00:00:00Z",
        evaluation_end="2024-11-04T00:00:00Z",
        outcome_as_of="2024-11-07T00:00:00Z",
    )
    first = payload["folds"][0]
    second = deepcopy(first)
    second["key"] = "other-instant"
    payload["folds"].append(second)
    for fold, origin in [(first, early), (second, late)]:
        fold["origin"] = fold["window_start"] = origin
        fold["window_end"] = origin.astimezone(UTC) + timedelta(days=2)
    receipt = register_synthetic_plan(payload)
    assert render(payload, receipt).evidence_status == "demonstration"

    payload["folds"] = [first]
    early_hash = render(payload, receipt).input_sha256
    first["origin"] = first["window_start"] = late
    first["window_end"] = late.astimezone(UTC) + timedelta(days=2)
    assert render(payload, receipt).input_sha256 != early_hash


def test_registration_must_precede_fit_even_without_development_rows(payload):
    fold = payload["folds"][0]
    fold["development"] = []
    fold["calibrated_at"] = None
    fold["protocol"]["available_at"] = fold["fitted_at"]
    report = render(payload, Registration.model_validate(fold["protocol"]))
    assert report.evidence_status == "blocked"
    assert [finding.code for finding in report.audits[0].findings] == ["protocol_after_origin"]


def test_actual_replay_publication_cannot_precede_simulated_availability(payload):
    fold = payload["folds"][0]
    fold["mode"] = "historical_replay"
    fold["issued_at"] = fold["forecast"]["available_at"] = "2000-01-09T23:59:59.999999Z"
    fold["replay_clock"] = {"issued_at": fold["origin"], "available_at": fold["origin"]}
    report = render(payload)
    assert report.evidence_status == "blocked"
    assert [finding.code for finding in report.audits[0].findings] == [
        "replay_publication_before_simulated_availability",
    ]


def test_zero_lead_case_cannot_attach_pr34_scores(payload):
    request = ReportRequest.model_validate(payload)
    assert request.folds[0].origin == request.folds[0].window_start
    assert render(payload).evidence_status == "demonstration"
    # PR #34 requires origin < start. Its output cannot override that mismatch.
    payload["comparisons"] = [{"case_indices": [0], "n": 1, "status": "comparable"}]
    with pytest.raises(ValidationError, match="comparisons"):
        ReportRequest.model_validate(payload)
