from uuid import uuid4

import pytest

from geointel.domain.models import AnalysisRun, Evidence, Forecast, ForecastSignal
from geointel.domain.schemas import ConflictType

QUESTION = (
    "Analyze the risk of organized political violence in Spain over the next 12 months, "
    "separated by conflict type."
)
REQUEST = {"location": "Spain", "question": QUESTION, "horizon_months": 12}
EXPECTED_TYPES = {item.value for item in ConflictType}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_request_validation(client):
    response = client.post(
        "/analysis", json={"location": "S", "question": "short", "horizon_months": 0}
    )
    assert response.status_code == 422


def test_whitespace_only_input_is_rejected(client):
    response = client.post(
        "/analysis", json={"location": "   ", "question": " " * 30, "horizon_months": 12}
    )
    assert response.status_code == 422


def test_spain_pipeline_persistence_retrieval_and_red_team(client, session):
    response = client.post("/analysis", json=REQUEST)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "completed"
    assert data["location"] == "Spain"
    assert data["horizon_months"] == 12
    assert len(data["forecast_ids"]) == 4
    assert data["red_team_output"]["false_positive_risks"]
    red_findings = {
        finding for findings in data["red_team_output"].values() for finding in findings
    }
    assert red_findings <= set(data["synthesis_output"]["incorporated_critiques"])
    metadata = data["collection_metadata"]
    assert metadata["connector_count"] == 4
    assert metadata["evidence_count"] == 0
    assert metadata["recent_event_count"] == 0
    assert metadata["forecast_signal_count"] == 0
    assert [x["connector"] for x in metadata["connector_outcomes"]] == [
        "UCDP",
        "VIEWS",
        "ACLED",
        "CAST",
    ]
    assert all(x["status"] == "disabled" for x in metadata["connector_outcomes"])
    assert metadata["external_collection_succeeded"] is False
    assert {item["conflict_type"] for item in data["synthesis_output"]["assessments"]} == (
        EXPECTED_TYPES
    )
    assert session.query(AnalysisRun).count() == 1
    assert session.query(Forecast).count() == 4
    assert client.get(f"/analysis/{data['id']}").json()["location"] == "Spain"
    forecasts = client.get("/forecasts").json()
    assert len(forecasts) == 4
    assert {item["conflict_type"] for item in forecasts} == EXPECTED_TYPES
    assert client.get(f"/forecasts/{forecasts[0]['id']}").status_code == 200


def test_missing_resources_return_404(client):
    assert client.get(f"/analysis/{uuid4()}").status_code == 404
    assert client.get(f"/forecasts/{uuid4()}").status_code == 404


def test_repeated_spain_analyses_preserve_forecast_history(client, session):
    first = client.post("/analysis", json=REQUEST).json()
    first_forecasts = {
        item["id"]: item
        for item in client.get("/forecasts").json()
        if item["analysis_run_id"] == first["id"]
    }

    second = client.post("/analysis", json=REQUEST).json()
    all_forecasts = client.get("/forecasts").json()
    second_ids = {item["id"] for item in all_forecasts if item["analysis_run_id"] == second["id"]}

    assert first["id"] != second["id"]
    assert set(first["forecast_ids"]).isdisjoint(second_ids)
    assert len(second_ids) == 4
    assert len(all_forecasts) == 8
    assert {
        item["id"]: item for item in all_forecasts if item["analysis_run_id"] == first["id"]
    } == first_forecasts
    assert session.query(AnalysisRun).count() == 2


def test_connector_outage_is_nonfatal_and_recorded(client, monkeypatch, session):
    class BrokenConnector:
        connector_name = "Broken"

        def collect(self, location, horizon_months):
            raise RuntimeError("upstream unavailable")

    monkeypatch.setattr("geointel.api.app.connectors", lambda: [BrokenConnector()])
    response = client.post("/analysis", json=REQUEST)

    assert response.status_code == 201
    metadata = response.json()["collection_metadata"]
    assert metadata["evidence_count"] == 0
    assert metadata["connector_failures"] == [
        {"connector": "Broken", "error": "upstream unavailable"}
    ]
    assert metadata["connector_outcomes"][0]["status"] == "failed"
    assert session.query(Evidence).count() == 0
    assert session.query(ForecastSignal).count() == 0


def test_pipeline_failure_rolls_back_all_partial_persistence(session):
    from geointel.domain.models import Location
    from geointel.domain.schemas import AnalysisRequest
    from geointel.pipeline.service import AnalysisPipeline
    from geointel.providers.base import ModelRouter

    class FailingModel:
        name = "failing-test-model"

        def generate(self, role, payload, output_type):
            raise RuntimeError("model failed")

    model = FailingModel()
    pipeline = AnalysisPipeline(session, ModelRouter(model, model))
    with pytest.raises(RuntimeError, match="model failed"):
        pipeline.run(AnalysisRequest.model_validate(REQUEST))

    assert session.query(Location).count() == 0
    assert session.query(AnalysisRun).count() == 0
    assert session.query(Forecast).count() == 0
