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
    EvaluationPanel,
    OutcomePublication,
    ReportPlan,
    ReportRequest,
    build_report,
    verify_report_v1,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def payload():
    return json.loads((FIXTURES / "synthetic_benchmark_request.json").read_text())


def registration():
    return Registration.model_validate_json(
        (FIXTURES / "synthetic_benchmark_registration.json").read_bytes()
    )


def render(payload, receipt=None, **evidence):
    return build_report(
        ReportRequest.model_validate(payload),
        verified_registration=receipt if receipt is not None else registration(),
        **evidence,
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
    assert report.panel_status == "unverified"
    assert report.outcome_publication_status == "unverified"
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
    fold["protocol"]["evidence_mode"] = mode
    fold["issued_at"] = fold["forecast"]["available_at"] = "2001-01-10T00:00:00Z"
    if mode == "historical_replay":
        fold["replay_clock"] = {"issued_at": fold["origin"], "available_at": fold["origin"]}
    report = render(payload, Registration.model_validate(fold["protocol"]))
    assert report.evidence_mode == mode
    assert report.evidence_status == status


@pytest.mark.parametrize(
    "mode", ["synthetic", "retrospective", "historical_archive", "prospective"]
)
def test_protocol_must_precede_first_development_decision(payload, mode):
    fold = payload["folds"][0]
    fold["mode"] = mode
    fold["protocol"]["evidence_mode"] = mode
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
    with pytest.raises(ValidationError, match="differs from registered evidence mode"):
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
    second["feature_inputs"][0].update(
        snapshot="synthetic:late-second-feature", available_at="2000-01-10T00:00:01Z"
    )
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
    fold["protocol"]["evidence_mode"] = fold["mode"]
    fold["issued_at"] = fold["forecast"]["available_at"] = "2001-01-10T00:00:00Z"
    fold["replay_clock"] = {
        "issued_at": fold["origin"],
        "available_at": "2000-01-10T00:00:01Z",
    }
    report = render(payload, Registration.model_validate(fold["protocol"]))
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
    fold["protocol"]["evidence_mode"] = fold["mode"]
    fold["issued_at"] = fold["forecast"]["available_at"] = "2000-01-09T23:59:59.999999Z"
    fold["replay_clock"] = {"issued_at": fold["origin"], "available_at": fold["origin"]}
    report = render(payload, Registration.model_validate(fold["protocol"]))
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


def test_single_fold_cannot_switch_to_retrospective_under_same_receipt(payload):
    fold = payload["folds"][0]
    fold["mode"] = "retrospective"
    fold["issued_at"] = fold["forecast"]["available_at"] = "2001-01-10T00:00:00Z"
    with pytest.raises(ValidationError, match="differs from registered evidence mode"):
        render(payload)
    fold["protocol"]["evidence_mode"] = "retrospective"
    with pytest.raises(ValueError, match="verified registration"):
        render(payload)


def test_registered_panel_accounts_for_present_missing_and_excluded_slots(payload):
    second = add_second_fold(payload)
    panel = EvaluationPanel(
        snapshot=payload["plan"]["panel_snapshot"],
        slots=(
            Fold.model_validate(payload["folds"][0]).evaluation_case().model_dump(),
            Fold.model_validate(second).evaluation_case().model_dump(),
            dict(
                geography_id=second["geography_id"],
                origin="2000-01-11T00:00:00Z",
                window_start="2000-01-11T00:00:00Z",
                window_end="2000-01-13T00:00:00Z",
                exclusion_reason="Registered coverage exclusion",
            ),
        ),
    )
    payload["plan"]["panel_sha256"] = panel.digest()
    receipt = register_synthetic_plan(payload)

    reversed_panel = EvaluationPanel(snapshot=panel.snapshot, slots=panel.slots[::-1])
    assert reversed_panel.digest() == panel.digest()
    full = render(payload, receipt, resolved_panel=reversed_panel)
    assert full.panel_status == "unverified"
    assert not full.missing_panel_slots
    assert full.resolved_panel == panel.canonical()
    payload["folds"].pop()
    partial = render(payload, receipt, resolved_panel=panel)
    assert partial.panel_status == "incomplete"
    assert partial.evidence_status == "blocked"
    assert partial.missing_panel_slots == (panel.slots[1].evaluation_case(),)
    assert render(payload, receipt).panel_status == "unverified"

    substituted = EvaluationPanel(snapshot=panel.snapshot, slots=panel.slots[:1])
    with pytest.raises(ValueError, match="differs from registered panel content"):
        render(payload, receipt, resolved_panel=substituted)

    fold = payload["folds"][0]
    fold.update(
        origin="2000-01-11T00:00:00Z",
        window_start="2000-01-11T00:00:00Z",
        window_end="2000-01-13T00:00:00Z",
    )
    with pytest.raises(ValueError, match="unregistered panel slot"):
        render(payload, receipt, resolved_panel=panel)
    fold["geography_id"] = second["geography_id"]
    with pytest.raises(ValueError, match="excluded panel slot"):
        render(payload, receipt, resolved_panel=panel)


def test_bare_panel_reference_cannot_verify_panel(payload):
    panel = EvaluationPanel.model_validate_json(
        (FIXTURES / "synthetic_benchmark_panel.json").read_bytes()
    )
    del payload["plan"]["panel_sha256"]
    receipt = register_synthetic_plan(payload)
    assert render(payload, receipt).panel_status == "unverified"
    with pytest.raises(ValueError, match="differs from registered panel content"):
        render(payload, receipt, resolved_panel=panel)
    with pytest.raises(ValidationError, match="duplicate registered panel slots"):
        EvaluationPanel.model_validate(
            dict(
                snapshot=panel.snapshot,
                slots=(
                    panel.slots[0],
                    dict(
                        panel.slots[0].model_dump(),
                        origin="2000-01-09T19:00:00-05:00",
                        exclusion_reason="Cannot declare the same slot twice",
                    ),
                ),
            )
        )


def test_verified_outcome_vintage_must_be_published_by_freeze(payload):
    payload["outcomes"]["outcome_snapshot"] = "selected-after-registration"
    declared = dict(
        payload["outcomes"],
        available_at="2000-01-14T19:00:00-05:00",
        availability_evidence="synthetic:publisher:release",
    )
    publication = OutcomePublication.model_validate(declared)
    assert publication.available_at > registration().available_at
    report = render(payload, verified_outcome_publication=publication)
    assert report.outcome_publication_status == "unverified"
    assert report.outcome_publication == publication
    assert not report.comparisons
    assert render(payload).outcome_publication_status == "unverified"

    late = OutcomePublication.model_validate(
        dict(declared, available_at="2000-01-15T00:00:00.000001Z")
    )
    with pytest.raises(ValueError, match="unavailable at the outcome freeze"):
        render(payload, verified_outcome_publication=late)
    wrong_vintage = OutcomePublication.model_validate(dict(declared, dataset_version="other"))
    with pytest.raises(ValueError, match="different outcome vintage"):
        render(payload, verified_outcome_publication=wrong_vintage)
    with pytest.raises(ValidationError, match="missing outcome publication evidence"):
        BenchmarkReport.model_validate(
            dict(render(payload).model_dump(), outcome_publication_status="verified")
        )


def test_canonical_development_duplicates_and_geographic_units(payload):
    fold = payload["folds"][0]
    alias = deepcopy(fold["development"][0])
    alias.update(
        key="different-key",
        geography_id=fold["geography_id"],
        origin="2000-01-01T19:00:00-05:00",
    )
    fold["development"].append(alias)
    report = render(payload)
    assert report.evidence_status == "blocked"
    assert [finding.code for finding in report.audits[0].findings] == ["duplicate_development_case"]

    alias["geography_id"] = "OTHER-UNIT"
    assert not render(payload).audits[0].findings

    alias["label"]["availability_evidence"] = "conflicting-log"
    with pytest.raises(ValidationError, match="conflicting snapshot declarations"):
        render(payload)
    constraints = StudyConstraints.model_validate(payload["plan"]["constraints"])
    assert [
        finding.code for finding in audit_fold(Fold.model_validate(fold), constraints).findings
    ] == ["conflicting_development_vintage"]
    alias["geography_id"] = fold["geography_id"]
    assert [
        finding.code for finding in audit_fold(Fold.model_validate(fold), constraints).findings
    ] == [
        "duplicate_development_case",
        "conflicting_development_vintage",
    ]


@pytest.fixture
def trusted_evidence(payload):
    panel = EvaluationPanel.model_validate_json(
        (FIXTURES / "synthetic_benchmark_panel.json").read_bytes()
    )
    request = ReportRequest.model_validate(payload)
    publication = OutcomePublication(
        **request.outcomes.model_dump(),
        availability_evidence="synthetic:publisher:release",
        available_at=request.plan.outcome_as_of,
    )
    return dict(
        original_request=request,
        registration=registration(),
        required_panel=panel,
        evidence_mode="synthetic",
        outcome_publication=publication,
        source_snapshots=(*request.snapshot_declarations(), publication.snapshot_declaration()),
    )


def render_with_evidence(evidence):
    return build_report(
        evidence["original_request"],
        verified_registration=evidence["registration"],
        resolved_panel=evidence["required_panel"],
        verified_outcome_publication=evidence["outcome_publication"],
    )


def test_reverify_serialized_manifest_with_external_evidence(trusted_evidence):
    report = render_with_evidence(trusted_evidence)
    parsed = BenchmarkReport.model_validate_json(report.model_dump_json())
    assert parsed.panel_status == parsed.outcome_publication_status == "unverified"
    result = verify_report_v1(parsed, **trusted_evidence)
    assert result.panel_status == result.outcome_publication_status == "verified"
    assert result.matches(parsed)
    changed = parsed.model_copy(update={"limitations": ("Changed scientific limitations.",)})
    assert not result.matches(changed)
    with pytest.raises(ValueError, match="report content differs"):
        verify_report_v1(changed, **trusted_evidence)


def test_v4_cannot_assert_verification_flags(trusted_evidence):
    report = render_with_evidence(trusted_evidence)
    for field in ("panel_status", "outcome_publication_status"):
        with pytest.raises(ValidationError):
            BenchmarkReport.model_validate(dict(report.model_dump(), **{field: "verified"}))


@pytest.fixture
def legacy_report():
    wire = (FIXTURES / "synthetic_benchmark_report_v3.json").read_bytes()
    data = json.loads(wire)
    assert data["schema_version"] == 3
    assert "dataset_version" not in data["registration"]
    assert data["panel_status"] == data["outcome_publication_status"] == "verified"
    return BenchmarkReport.model_validate_json(wire)


def test_genuine_v3_manifest_migrates_and_reverifies(legacy_report, trusted_evidence):
    assert legacy_report.schema_version == 4
    assert legacy_report.panel_status == legacy_report.outcome_publication_status == "unverified"
    wire = legacy_report.model_dump_json()
    assert json.loads(wire)["schema_version"] == 4
    migrated = BenchmarkReport.model_validate_json(wire)
    assert migrated == render_with_evidence(trusted_evidence)
    result = verify_report_v1(migrated, **trusted_evidence)
    assert result.panel_status == result.outcome_publication_status == "verified"
    assert result.matches(legacy_report)


def test_genuine_v3_accepts_additional_authenticated_metadata(legacy_report, trusted_evidence):
    sources = trusted_evidence["source_snapshots"]
    receipt = trusted_evidence["registration"].model_copy(update={"dataset_version": "registry-v1"})
    feature = next(source for source in sources if source.snapshot == "synthetic:train-feature")
    enriched = feature.model_copy(
        update={"dataset_version": "features-v1", "issued_at": feature.available_at}
    )
    trusted_evidence.update(
        registration=receipt,
        source_snapshots=tuple(
            enriched if source.snapshot == feature.snapshot else source for source in sources
        ),
    )
    result = verify_report_v1(legacy_report, **trusted_evidence)
    assert result.panel_status == "verified"
    assert result.matches(legacy_report)
    assert legacy_report.registration.dataset_version is None


@pytest.mark.parametrize("version", [None, "contradictory"])
def test_populated_request_version_requires_trusted_agreement(payload, trusted_evidence, version):
    payload["folds"][0]["forecast"]["dataset_version"] = "declared"
    request = ReportRequest.model_validate(payload)
    publication = trusted_evidence["outcome_publication"]
    sources = (*request.snapshot_declarations(), publication.snapshot_declaration())
    trusted_evidence.update(original_request=request, source_snapshots=sources)
    report = render_with_evidence(trusted_evidence)
    assert verify_report_v1(report, **trusted_evidence).matches(report)
    trusted_evidence["source_snapshots"] = tuple(
        source.model_copy(update={"dataset_version": version})
        if source.issued_at is not None
        else source
        for source in sources
    )
    with pytest.raises(ValueError, match="source snapshot evidence differs"):
        verify_report_v1(report, **trusted_evidence)


def test_genuine_v3_rejects_contradictory_trusted_records(legacy_report, trusted_evidence):
    snapshots = trusted_evidence["source_snapshots"]
    receipt = trusted_evidence["registration"]
    resolved = next(source for source in snapshots if source.snapshot == receipt.snapshot)
    trusted_evidence["registration"] = receipt.model_copy(update={"dataset_version": "v1"})
    trusted_evidence["source_snapshots"] = (
        *snapshots,
        resolved.model_copy(update={"dataset_version": "v2"}),
    )
    with pytest.raises(ValueError, match="conflicting snapshot declarations"):
        verify_report_v1(legacy_report, **trusted_evidence)

    trusted_evidence["registration"] = receipt
    trusted_evidence["source_snapshots"] += (resolved.model_copy(update={"dataset_version": "v1"}),)
    with pytest.raises(ValueError, match="conflicting snapshot declarations"):
        verify_report_v1(legacy_report, **trusted_evidence)


def test_verify_requires_original_request(trusted_evidence):
    report = render_with_evidence(trusted_evidence)
    del trusted_evidence["original_request"]
    with pytest.raises(TypeError, match="original_request"):
        verify_report_v1(report, **trusted_evidence)


@pytest.mark.parametrize(
    ("key", "field", "value", "message"),
    [
        ("registration", "availability_evidence", "unrelated", "verified registration"),
        ("outcome_publication", "availability_evidence", "unrelated", "snapshot evidence differs"),
    ],
)
def test_verification_rejects_incorrect_external_evidence(
    trusted_evidence, key, field, value, message
):
    report = render_with_evidence(trusted_evidence)
    trusted_evidence[key] = trusted_evidence[key].model_copy(update={field: value})
    with pytest.raises(ValueError, match=message):
        verify_report_v1(report, **trusted_evidence)


def test_verify_rejects_audit_membership_changed_after_build(trusted_evidence):
    report = render_with_evidence(trusted_evidence)
    audit = report.audits[0].model_copy(update={"fold_key": "unregistered-fold"})
    changed = BenchmarkReport.model_validate(dict(report.model_dump(), audits=(audit,)))
    with pytest.raises(ValueError, match="audits differ"):
        verify_report_v1(changed, **trusted_evidence)


def test_verify_rejects_embedded_publication_with_different_evidence(trusted_evidence):
    report = render_with_evidence(trusted_evidence)
    publication = trusted_evidence["outcome_publication"].model_copy(
        update={"availability_evidence": "unrelated-source"}
    )
    changed = BenchmarkReport.model_validate(
        dict(report.model_dump(), outcome_publication=publication)
    )
    assert changed.outcome_publication_status == "unverified"
    with pytest.raises(ValueError, match="report content differs"):
        verify_report_v1(changed, **trusted_evidence)


@pytest.mark.parametrize("change", ["missing", "timestamp", "issue_time", "source_reference"])
def test_verify_rejects_changed_source_metadata(trusted_evidence, change):
    report = render_with_evidence(trusted_evidence)
    snapshots = trusted_evidence["source_snapshots"]
    forecast = next(source for source in snapshots if source.issued_at is not None)
    other = tuple(source for source in snapshots if source.snapshot != forecast.snapshot)
    updates = {
        "timestamp": {"available_at": forecast.available_at + timedelta(microseconds=1)},
        "source_reference": {"availability_evidence": "different"},
        "issue_time": {"issued_at": forecast.issued_at - timedelta(microseconds=1)},
    }
    trusted_evidence["source_snapshots"] = (
        other if change == "missing" else (*other, forecast.model_copy(update=updates[change]))
    )
    with pytest.raises(ValueError, match="source snapshot evidence differs"):
        verify_report_v1(report, **trusted_evidence)


def test_verification_rejects_incorrect_trusted_mode(trusted_evidence):
    report = render_with_evidence(trusted_evidence)
    with pytest.raises(ValueError, match="trusted evidence mode"):
        verify_report_v1(report, **dict(trusted_evidence, evidence_mode="retrospective"))


def test_cross_fold_label_timestamps_must_agree(payload):
    first_label = payload["folds"][0]["development"][0]["label"]
    first_label["available_at"] = "2000-01-05T00:00:00.000001Z"
    payload["folds"][0]["fitted_at"] = "2000-01-05T00:00:00.000001Z"
    second = add_second_fold(payload)
    second["development"][0]["label"]["available_at"] = "2000-01-05T00:00:00Z"
    receipt = register_synthetic_plan(payload)
    constraints = StudyConstraints.model_validate(payload["plan"]["constraints"])
    assert all(
        not audit_fold(Fold.model_validate(fold), constraints).findings for fold in payload["folds"]
    )
    with pytest.raises(ValidationError, match="conflicting snapshot declarations"):
        render(payload, receipt)


@pytest.mark.parametrize(
    "changes",
    [
        {"available_at": "2000-01-05T00:00:00.000001Z"},
        {"dataset_version": "v2"},
    ],
)
def test_development_evaluation_metadata_must_agree(payload, changes):
    fold = payload["folds"][0]
    label = fold["development"][0]["label"]
    label["dataset_version"] = "v1"
    fold["feature_inputs"] = [dict(label, **changes)]
    constraints = StudyConstraints.model_validate(payload["plan"]["constraints"])
    assert [
        finding.code for finding in audit_fold(Fold.model_validate(fold), constraints).findings
    ] == [
        "conflicting_snapshot_declarations",
    ]
    with pytest.raises(ValidationError, match="conflicting snapshot declarations"):
        render(payload)


def test_outcome_snapshot_metadata_must_match_development(payload):
    label = payload["folds"][0]["development"][0]["label"]
    payload["outcomes"]["outcome_snapshot"] = label["snapshot"]
    label["dataset_version"] = payload["outcomes"]["dataset_version"]
    publication = OutcomePublication.model_validate(
        dict(
            payload["outcomes"],
            available_at=label["available_at"],
            availability_evidence=label["availability_evidence"],
        )
    )
    render(payload, verified_outcome_publication=publication)
    wrong_time = publication.model_copy(
        update={"available_at": publication.available_at + timedelta(microseconds=1)}
    )
    with pytest.raises(ValueError, match="conflicting snapshot declarations"):
        render(payload, verified_outcome_publication=wrong_time)
    label["dataset_version"] = "different"
    with pytest.raises(ValueError, match="conflicting snapshot declarations"):
        render(payload)


def test_repeated_snapshot_is_valid_across_roles_folds_and_geographies(payload):
    first = payload["folds"][0]
    first["feature_inputs"] = [deepcopy(first["development"][0]["label"])]
    second = add_second_fold(payload)
    second["feature_inputs"][0]["available_at"] = "2000-01-04T19:00:00-05:00"
    report = render(payload, register_synthetic_plan(payload))
    assert {audit.evaluation_case.geography_id for audit in report.audits} == {"EXAMPLE", "SECOND"}
    assert all(not audit.findings for audit in report.audits)


def test_complete_manifest_cannot_verify_against_incomplete_original(payload, trusted_evidence):
    add_second_fold(payload)
    panel = EvaluationPanel(
        snapshot=payload["plan"]["panel_snapshot"],
        slots=tuple(
            Fold.model_validate(fold).evaluation_case().model_dump() for fold in payload["folds"]
        ),
    )
    payload["plan"]["panel_sha256"] = panel.digest()
    receipt = register_synthetic_plan(payload)
    full_request = ReportRequest.model_validate(payload)
    full_evidence = dict(
        trusted_evidence,
        original_request=full_request,
        required_panel=panel,
        registration=receipt,
        source_snapshots=(
            *full_request.snapshot_declarations(),
            trusted_evidence["outcome_publication"].snapshot_declaration(),
        ),
    )
    complete = render_with_evidence(full_evidence)
    payload["folds"].pop()
    partial_evidence = dict(full_evidence, original_request=ReportRequest.model_validate(payload))
    incomplete = render_with_evidence(partial_evidence)
    result = verify_report_v1(incomplete, **partial_evidence)
    assert result.panel_status == "incomplete"
    assert result.outcome_publication_status == "verified"
    assert result.scoring_status == "unsupported"
    assert not incomplete.comparisons
    assert incomplete.evidence_status == "blocked"
    assert complete.panel_status == "unverified"
    legacy_claim = BenchmarkReport.model_validate(
        dict(
            complete.model_dump(),
            schema_version=3,
            input_sha256=incomplete.input_sha256,
            panel_status="verified",
            outcome_publication_status="verified",
        )
    )
    assert legacy_claim.panel_status == legacy_claim.outcome_publication_status == "unverified"
    with pytest.raises(ValueError, match="audits differ"):
        verify_report_v1(legacy_claim, **partial_evidence)


def test_publication_at_freeze_never_grants_scoring_eligibility(legacy_report, trusted_evidence):
    assert trusted_evidence["outcome_publication"].available_at == legacy_report.plan.outcome_as_of
    result = verify_report_v1(legacy_report, **trusted_evidence)
    assert result.panel_status == result.outcome_publication_status == "verified"
    assert result.scoring_status == "unsupported"
    assert not legacy_report.comparisons


def test_timely_publication_does_not_override_outcome_maturity(payload, trusted_evidence):
    payload["plan"]["constraints"]["outcome_maturity"] = "P4D"
    receipt = register_synthetic_plan(payload)
    assert trusted_evidence["outcome_publication"].available_at.isoformat() == (
        "2000-01-15T00:00:00+00:00"
    )
    with pytest.raises(ValidationError, match="has not matured by the outcome freeze"):
        render(
            payload, receipt, verified_outcome_publication=trusted_evidence["outcome_publication"]
        )
