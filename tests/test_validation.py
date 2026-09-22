import json
import subprocess
import sys
from uuid import UUID

from sqlalchemy import select

from geointel.domain.models import (
    AnalysisRun,
    Event,
    Forecast,
    ValidationResult,
    ValidationRun,
)
from geointel.validation.domain import AssertionType, ValidationCase
from geointel.validation.runner import ValidationRunner
from geointel.validation.suite import load_suite

EXPECTED_CASES = ["spain", "georgia", "taiwan", "serbia", "nigeria"]


def test_five_country_suite_is_stable_synthetic_and_not_a_ranking():
    suite = load_suite()
    assert suite.suite_id == "five-country-v1"
    assert suite.synthetic is True
    assert [case.case_id for case in suite.cases] == EXPECTED_CASES
    assert len(suite.cases) == 5
    assert all(len(case.conflict_categories) == 4 for case in suite.cases)
    dumped = suite.model_dump()
    assert "ranking" not in json.dumps(dumped).lower()
    assert "risk_label" not in ValidationCase.model_fields
    assert set(AssertionType) == set(suite.cases[0].assertions)


def test_complete_suite_runs_normal_offline_pipeline_and_persists_audit(session):
    output = ValidationRunner(session).run()
    assert [item["case_id"] for item in output["cases"]] == EXPECTED_CASES
    assert output["summary"]["fail"] == 0
    assert output["summary"]["error"] == 0
    assert session.query(AnalysisRun).count() == 5
    assert session.query(ValidationRun).count() == 5
    assert session.query(ValidationResult).count() == 5 * len(AssertionType)
    for item in output["cases"]:
        run = session.get(ValidationRun, UUID(item["validation_run_id"]))
        assert run.analysis_run_id
        assert run.analysis_run.provider_config["reasoning_model"] == "offline-rules-v1"
        assert run.source_matrix.keys() == {"UCDP", "ACLED", "VIEWS", "CAST", "Strategic Knowledge"}


def test_spain_control_and_metamorphic_disclosures(session):
    spain = ValidationRunner(session).run(case_id="spain")["cases"][0]
    results = {x["assertion"]: x["status"] for x in spain["results"]}
    assert results["CONTROL_FALSE_POSITIVE_GUARD"] == "pass"
    assert results["NO_SINGLE_EVENT_ESCALATION"] == "pass"
    assert results["MISSING_SOURCE_DISCLOSED"] == "pass"
    assert results["RED_TEAM_CONSIDERS_BIAS"] == "pass"
    run = session.get(AnalysisRun, UUID(spain["analysis_run_id"]))
    assert all(item["probability_low"] is None for item in run.synthesis_output["assessments"])
    assert set(item["conflict_type"] for item in run.synthesis_output["assessments"]) == {
        "interstate_armed_conflict",
        "internal_armed_conflict",
        "one_sided_violence",
        "major_political_violence",
    }


def test_disagreement_stale_geography_failure_and_high_volume_are_bounded(session):
    output = ValidationRunner(session).run()
    cases = {x["case_id"]: x for x in output["cases"]}
    assert cases["georgia"]["source_matrix"]["UCDP"]["stale"]
    georgia = session.get(AnalysisRun, UUID(cases["georgia"]["analysis_run_id"]))
    assert georgia.analyst_output["source_disagreements"]
    serbia = session.get(AnalysisRun, UUID(cases["serbia"]["analysis_run_id"]))
    assert "CAST" in serbia.analyst_output["missing_sources"]
    assert serbia.red_team_output["geographic_mismatches"]
    nigeria = session.get(AnalysisRun, UUID(cases["nigeria"]["analysis_run_id"]))
    events = list(session.scalars(select(Event).where(Event.analysis_run_id == nigeria.id)))
    assert len(events) == 40  # exact duplicate removed, bounded fixture retained
    assert events[0].provenance["provenance"]["fatalities_uncertain"] is True


def test_repeated_runs_preserve_history_and_forecasts(session):
    runner = ValidationRunner(session)
    first = runner.run(case_id="spain")["cases"][0]
    second = runner.run(case_id="spain")["cases"][0]
    assert first["analysis_run_id"] != second["analysis_run_id"]
    assert first["validation_run_id"] != second["validation_run_id"]
    assert session.query(Forecast).count() == 8


def test_cli_json_output_is_machine_readable(tmp_path):
    db = tmp_path / "validation.db"
    command = [
        sys.executable,
        "-m",
        "geointel.validation",
        "run",
        "five-country-v1",
        "--case",
        "spain",
        "--json",
    ]
    completed = subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
        env={**__import__("os").environ, "DATABASE_URL": f"sqlite:///{db}"},
    )
    output = json.loads(completed.stdout)
    assert output["suite"] == "five-country-v1"
    assert output["cases"][0]["case_id"] == "spain"
