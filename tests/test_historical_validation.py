import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from geointel.historical_validation.report import (
    BenchmarkReport,
    ReportRequest,
    Sample,
    build_report,
)


@pytest.fixture
def payload():
    path = Path(__file__).parent / "fixtures" / "synthetic_benchmark_request.json"
    return json.loads(path.read_text())


def test_synthetic_report_round_trip(payload):
    request = ReportRequest.model_validate(payload)
    report = build_report(request)
    assert report.evidence_mode == "synthetic"
    assert report.evidence_status == "demonstration"
    assert not report.audits[0].findings
    assert report.model_dump_json() == build_report(request).model_dump_json()
    assert BenchmarkReport.model_validate_json(report.model_dump_json()) == report
    assert "evidence_status" in BenchmarkReport.model_json_schema()["properties"]


@pytest.mark.parametrize(
    ("field", "index", "timestamp", "finding"),
    [
        ("features", 0, "2000-01-02T00:00:00.000001Z", "feature_after_cutoff"),
        ("label", 0, "2000-01-05T00:00:00.000001Z", "label_after_fit"),
        ("label", 1, "2000-01-07T23:59:59Z", "label_before_window_end"),
    ],
)
def test_revision_and_label_boundaries(payload, field, index, timestamp, finding):
    vintage = payload["folds"][0]["development"][index][field]
    if field == "features":
        vintage = vintage[0]
    vintage["available_at"] = timestamp
    report = build_report(ReportRequest.model_validate(payload))
    assert report.evidence_status == "blocked"
    assert finding in {record.code for record in report.audits[0].findings}


def test_embargo_rejects_gap_even_with_mature_label(payload):
    payload["folds"][0]["embargo"] = "P2DT1S"
    report = build_report(ReportRequest.model_validate(payload))
    assert [finding.code for finding in report.audits[0].findings] == [
        "development_window_overlap",
        "development_window_overlap",
    ]


@pytest.mark.parametrize(
    ("mode", "status"),
    [
        ("retrospective", "descriptive"),
        ("historical_replay", "provenance_review_required"),
        ("historical_archive", "blocked"),
        ("prospective", "blocked"),
    ],
)
def test_later_forecast_keeps_evidence_mode(payload, mode, status):
    fold = payload["folds"][0]
    fold["mode"] = mode
    fold["issued_at"] = fold["forecast"]["available_at"] = "2001-01-10T00:00:00Z"
    report = build_report(ReportRequest.model_validate(payload))
    assert report.evidence_mode == mode
    assert report.evidence_status == status


def test_prospective_protocol_must_exist_at_origin(payload):
    fold = payload["folds"][0]
    fold["mode"] = "prospective"
    fold["protocol"]["available_at"] = "2000-01-11T00:00:00Z"
    report = build_report(ReportRequest.model_validate(payload))
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
    payload["folds"].append(dict(payload["folds"][0], key="second", mode="historical_replay"))
    with pytest.raises(ValidationError, match="single evidence mode"):
        ReportRequest.model_validate(payload)


def test_empty_and_imbalanced_samples():
    assert Sample(eligible_slots=0, scored=0, events=0, exclusions={}).events == 0
    rare = Sample(eligible_slots=102, scored=100, events=1, exclusions={"missing": 2})
    assert rare.events == 1
    with pytest.raises(ValidationError, match="do not reconcile"):
        Sample(eligible_slots=102, scored=100, events=1, exclusions={"missing": 1})


def test_blocked_report_withholds_score_attachment(payload):
    payload["comparisons"] = [
        {
            "model": "fictional model",
            "version": "1",
            "forecast_snapshot": "synthetic:forecast",
            "baseline": "fictional baseline",
            "baseline_version": "1",
            "baseline_snapshot": "synthetic:baseline",
            "matched_keys": "a" * 64,
            "sample": {"eligible_slots": 0, "scored": 0, "events": 0, "exclusions": {}},
            "metrics_artifact": "synthetic:empty-artifact",
            "calibration_artifact": None,
            "uncertainty_artifact": None,
        }
    ]
    clean = build_report(ReportRequest.model_validate(payload))
    payload["folds"][0]["feature_inputs"][0]["available_at"] = "2000-01-11T00:00:00Z"
    blocked = build_report(ReportRequest.model_validate(payload))
    assert len(clean.comparisons) == 1
    assert blocked.comparisons == ()
    assert clean.input_sha256 != blocked.input_sha256


def test_inconsistent_evidence_status_is_rejected(payload):
    report = build_report(ReportRequest.model_validate(payload)).model_dump()
    report["evidence_status"] = "provenance_review_required"
    with pytest.raises(ValidationError, match="evidence status conflicts"):
        BenchmarkReport.model_validate(report)
