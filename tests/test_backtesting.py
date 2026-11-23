import json
import math
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from geointel.backtesting import (
    Case,
    Contract,
    ModelArchive,
    Observation,
    Prediction,
    Study,
    Threshold,
    evaluate,
)


def date(month, day=1):
    return datetime(2020, month, day, tzinfo=UTC)


def study_for(values=(1.0, 0.0), *, kind="binary_probability"):
    contract = Contract(
        target="synthetic.battles.v1", geographic_unit="country", horizon_months=1, kind=kind
    )
    cases = tuple(
        Case(location=location, origin=date(1), start=date(2), end=date(3))
        for location in ("AAA", "BBB")
    )
    predictions = tuple(
        Prediction(
            case=case,
            contract=contract,
            record_id=f"prediction-{i}",
            issued_at=date(1),
            available_at=date(1),
            input_cutoff=date(1),
            value=value,
        )
        for i, (case, value) in enumerate(zip(cases, values, strict=True))
    )
    observations = tuple(
        Observation(
            contract=contract,
            location=case.location,
            start=case.start,
            end=case.end,
            record_id=f"observation-{i}",
            available_at=date(3),
            complete=True,
            value=value,
        )
        for i, (case, value) in enumerate(zip(cases, (1, 0), strict=True))
    )
    return Study(
        contract=contract,
        panel_snapshot="synthetic-panel-v1",
        cases=cases,
        models=(
            ModelArchive(
                model="example", version="1", snapshot="synthetic-v1", predictions=predictions
            ),
        ),
        outcome_snapshot="synthetic-outcomes-v1",
        observations=observations,
        as_of=date(4),
        data_kind="synthetic",
    )


def change_predictions(study, *rows):
    return study.model_copy(
        update={"models": (study.models[0].model_copy(update={"predictions": rows}),)}
    )


@pytest.mark.parametrize(
    ("values", "brier", "loss", "f1"),
    [
        ((1.0, 0.0), 0, 0, 1),
        ((0.0, 1.0), 1, -math.log(1e-15), 0),
    ],
)
def test_binary_scores(values, brier, loss, f1):
    study = study_for(values).model_copy(
        update={
            "threshold": Threshold(value=0.5, rationale="Predeclared synthetic decision rule"),
        }
    )
    report = evaluate(study)
    metrics = report["models"][0]["metrics"]
    assert metrics["brier"] == brier
    assert metrics["log_loss"] == pytest.approx(loss)
    assert metrics["classification"]["f1"] == f1
    assert metrics["classification"]["precision"] == f1
    assert metrics["classification"]["recall"] == f1
    assert metrics["calibration"][9]["mean_prediction"] == 1
    assert metrics["calibration"][0]["observed_frequency"] == brier
    assert metrics["small_sample"]
    assert report["data_kind"] == "synthetic"


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        (None, "missing"),
        ({"complete": False, "value": 0}, "incomplete"),
        ({"value": None}, "missing_value"),
        ({"available_at": date(5)}, "unavailable_as_of"),
        ({"available_at": date(2, 15)}, "premature"),
        ({"location": "CCC"}, "missing"),
    ],
)
def test_missing_or_ineligible_outcomes(changes, status):
    study = study_for()
    one, two = study.observations
    observations = (one,) if changes is None else (one, two.model_copy(update=changes))
    report = evaluate(study.model_copy(update={"observations": observations}))
    assert report["coverage"]["outcome_statuses"] == {"eligible": 1, status: 1}
    assert report["models"][0]["metrics"]["n"] == 1
    assert report["models"][0]["scored_coverage"] == 0.5


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        ({"available_at": date(1, 2)}, "invalid_timing"),
        ({"issued_at": date(2)}, "invalid_timing"),
        ({"input_cutoff": date(3)}, "invalid_timing"),
        ({"value": float("nan")}, "invalid_value"),
        ({"value": float("inf")}, "invalid_value"),
        ({"value": -0.1}, "invalid_value"),
        ({"value": 1.1}, "invalid_value"),
        ({"value": None}, "missing_value"),
    ],
)
def test_ineligible_predictions(changes, status):
    study = study_for()
    one, two = study.models[0].predictions
    report = evaluate(change_predictions(study, one, two.model_copy(update=changes)))
    assert report["models"][0]["prediction_statuses"] == {"eligible": 1, status: 1}


@pytest.mark.parametrize(
    "changes",
    [
        {"horizon_months": 2},
        {"geographic_unit": "admin1"},
        {"target": "another target"},
        {"kind": "event_count"},
    ],
)
def test_incompatible_contracts(changes):
    study = study_for()
    one, two = study.models[0].predictions
    incompatible = study.contract.model_copy(update=changes)
    with pytest.raises(ValueError, match="incompatible prediction contract"):
        evaluate(change_predictions(study, one, two.model_copy(update={"contract": incompatible})))


def test_outside_panel_prediction():
    study = study_for()
    prediction = study.models[0].predictions[0]
    wrong_case = prediction.case.model_copy(update={"location": "CCC"})
    report = evaluate(change_predictions(study, prediction.model_copy(update={"case": wrong_case})))
    model = report["models"][0]
    assert model["prediction_statuses"] == {"missing": 2}
    assert model["outside_panel"] == 1
    assert model["metrics"]["brier"] is None


def test_comparison_uses_only_shared_cases():
    study = study_for((0.0, 0.0))
    model = study.models[0]
    two = model.predictions[1]
    other = model.model_copy(update={"model": "other", "predictions": (two,)})
    report = evaluate(study.model_copy(update={"models": (model, other)}))
    assert report["models"][0]["metrics"]["brier"] == 0.5
    comparison = report["comparison"]
    assert comparison["case_indices"] == [1]
    assert [entry["metrics"]["brier"] for entry in comparison["models"]] == [0, 0]


def test_disjoint_models_have_no_comparison_scores():
    study = study_for()
    model = study.models[0]
    one, two = model.predictions
    left = model.model_copy(update={"predictions": (one,)})
    right = model.model_copy(update={"model": "other", "predictions": (two,)})
    comparison = evaluate(study.model_copy(update={"models": (left, right)}))["comparison"]
    assert comparison["status"] == "no_shared_cases"
    assert comparison["models"] == []


def test_count_scores():
    report = evaluate(study_for((2.5, 0), kind="event_count"))
    assert report["models"][0]["metrics"] == {"n": 2, "small_sample": True, "mae": 0.75}


def test_cli_is_reproducible(tmp_path):
    path = tmp_path / "study.json"
    study = study_for()
    path.write_text(study.model_dump_json(), encoding="utf-8")
    command = [sys.executable, "-m", "geointel.backtesting", str(path)]
    first = subprocess.check_output(command)
    assert first == subprocess.check_output(command)
    assert json.loads(first) == evaluate(study)


def test_open_window_without_observation():
    study = study_for().model_copy(update={"as_of": date(2, 15), "observations": ()})
    report = evaluate(study)
    assert report["coverage"]["outcome_statuses"] == {"window_open_as_of": 2}
    assert report["models"][0]["metrics"]["n"] == 0
