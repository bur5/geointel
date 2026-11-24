from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from geointel.api import dashboard
from geointel.api.app import dashboard_app
from geointel.api.dashboard_schemas import Observation, Overview, Page, Prediction
from geointel.domain.database import get_session
from geointel.domain.models import (
    AnalysisRun,
    Event,
    Evidence,
    Forecast,
    ForecastSignal,
    Indicator,
    Location,
    Source,
)

PREFIX = "/api/v1/dashboard"


def moment(month, day=1):
    return datetime(2025, month, day, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(dashboard, "utcnow", lambda: moment(8))


@pytest.fixture
def records(session):
    spain = Location(name="Kingdom of Spain")
    serbia = Location(name="Synthetic label", iso_code="RS")
    source = Source(name="Synthetic Provider", source_type="operational_events")
    ucdp = Source(name="UCDP", source_type="structured_data")
    session.add_all([spain, serbia, source, ucdp])
    session.flush()
    run = AnalysisRun(
        location_id=spain.id,
        question="private analysis question",
        horizon_months=3,
        status="completed",
        pipeline_version="synthetic-v1",
        provider_config={"token": "private-value"},
    )
    session.add(run)
    session.flush()
    for number, when, location, details in (
        (1, moment(7), spain, {}),
        (2, moment(7), spain, {}),
        (3, moment(4), spain, {}),
        (4, moment(7), serbia, {}),
        (5, None, spain, {}),
        (6, moment(6), None, {}),
        (7, moment(7), spain, {"country": "Nigeria"}),
    ):
        session.add(
            Event(
                id=UUID(int=number),
                source_id=source.id,
                source_record_id=f"synthetic-event-{number}",
                location_id=location.id if location else None,
                occurred_at=when,
                event_type="synthetic",
                description="private description",
                confidence="reported",
                provenance=details | {"private_key": "private-value"},
            )
        )
    for number, when, role in (
        (1, moment(2), "annual_historical"),
        (2, moment(7), "candidate_recent"),
        (3, moment(8), "unclassified"),
    ):
        session.add(
            Evidence(
                analysis_run_id=run.id,
                source_id=ucdp.id,
                location_id=serbia.id,
                source_record_id=f"synthetic-ucdp-{number}",
                title="synthetic",
                summary="synthetic",
                event_date=when,
                retrieved_at=moment(7),
                reliability="high",
                provenance={
                    "country": "Spain",
                    "dataset": "synthetic GED",
                    "dataset_version": "test-1",
                    "temporal_role": role,
                    "date_end": when.isoformat(),
                    "coverage_end": "2025-06-01",
                    "fatalities": {"best": 2, "low": 1, "high": 4},
                },
            )
        )
    for when, value in ((moment(1), 3.0), (moment(7), None)):
        session.add(
            Indicator(
                location_id=spain.id,
                name="synthetic indicator",
                value=value,
                unit="synthetic units",
                observed_at=when,
                provenance={"provider": "Synthetic Provider", "record_id": "example"},
            )
        )
    for geography_unit, country in (("country", "Spain"), ("admin1", "Spain")):
        session.add(
            ForecastSignal(
                analysis_run_id=run.id,
                location_id=spain.id,
                provider="Synthetic Provider",
                source_record_id=f"synthetic-{geography_unit}",
                model_name="test model",
                model_version="test-1",
                geographic_unit=geography_unit,
                source_location=country,
                issue_date=moment(5),
                target_start=moment(7),
                target_end=moment(9),
                horizon_months=3,
                target_variable="synthetic target",
                prediction=2.5,
                unit="native event count",
                scale="monthly",
                retrieved_at=moment(6),
                source_url="https://example.invalid/?token=private-value",
                alignment_status="aligned",
                alignment_notes=[],
                provenance={"private_key": "private-value"},
            )
        )
    session.add(
        Forecast(
            analysis_run_id=run.id,
            created_at=moment(6),
            conflict_type="synthetic category",
            question=run.question,
            horizon_months=3,
            probability_low=None,
            probability_high=None,
            confidence="low",
            rationale="private description",
            evidence_for=[],
            evidence_against=[],
            unknowns=[],
            resolution_criteria=[],
            change_conditions=[],
        )
    )
    session.commit()
    return run.id


@pytest.mark.parametrize(
    "query",
    [
        "country=ZZ",
        "country=ABC",
        "country=Spain",
        "region=unknown",
        "country=ESP&region=western-asia",
        "start=2025-05-01&end=2025-05-01",
        "start=2025-07-01&end=2025-05-01",
        "start=not-a-date",
        "limit=0",
        "limit=201",
        "offset=10001",
    ],
)
def test_invalid_filters(client, query):
    assert client.get(f"{PREFIX}/observations?{query}").status_code == 422


def test_country_region_and_missing_geography(client, records):
    response = client.get(f"{PREFIX}/regions/southern-europe")
    assert response.status_code == 200
    countries = response.json()["countries"]
    assert [value["coverage"]["country"] for value in countries] == ["ESP", "SRB"]
    assert countries[1]["observation"]["geography"]["iso3"] == "SRB"
    assert countries[1]["prediction"] is None
    assert client.get(f"{PREFIX}/regions/unknown").status_code == 422
    assert client.get(f"{PREFIX}/countries/ZZ").status_code == 422
    country = client.get(f"{PREFIX}/countries/es").json()
    assert country["coverage"]["country"] == "ESP"
    assert country["observation"]["id"] == str(UUID(int=1))
    region = client.get(f"{PREFIX}/observations?region=southern-europe").json()
    assert {item["geography"]["iso3"] for item in region["items"]} == {"ESP", "SRB"}
    items = client.get(f"{PREFIX}/observations").json()["items"]
    unknown = next(item for item in items if item["id"] == str(UUID(int=6)))
    assert unknown["geography"] == dict(name=None, iso3=None, region=None, unit=None)
    assert items[-1]["occurred_at"] is None
    assert items[-1]["freshness"] == "unknown"
    nigeria = client.get(f"{PREFIX}/observations?country=NG").json()["items"]
    assert [item["id"] for item in nigeria] == [str(UUID(int=7))]


def test_empty_database_and_missing_forecast(client):
    response = client.get(f"{PREFIX}/overview")
    assert response.status_code == 200
    overview = Overview.model_validate(response.json())
    assert overview.observation is None
    assert overview.prediction is None
    assert overview.coverage.predictions.availability == "missing"
    assert overview.coverage.observations.latest_at is None
    assert client.get(f"{PREFIX}/coverage?country=ca").json()["country"] == "CAN"
    assert client.get(f"{PREFIX}/forecasts").json() == {
        "items": [],
        "availability": "missing",
        "limit": 50,
        "offset": 0,
        "next_offset": None,
    }


def test_historical_window_and_pagination(client, records):
    query = f"{PREFIX}/observations?country=ES&start=2025-04-01&end=2025-08-01&limit=1"
    for offset, event_id, next_offset in ((0, 1, 1), (1, 2, 2), (2, 3, None)):
        response = client.get(f"{query}&offset={offset}")
        assert response.status_code == 200
        result = Page[Observation].model_validate(response.json())
        assert [item.id for item in result.items] == [UUID(int=event_id)]
        assert result.next_offset == next_offset
        assert result.items[0].freshness == ("stale" if event_id == 3 else "recent")
    assert client.get(f"{query}&offset=3").json()["availability"] == "end_of_results"
    april = client.get(f"{PREFIX}/observations?country=ESP&end=2025-07-01").json()["items"]
    assert [item["id"] for item in april] == [str(UUID(int=3))]


def test_ucdp_records_preserve_source_role_and_uncertainty(client, records):
    data = client.get(f"{PREFIX}/ucdp-observations?country=ESP").json()
    assert [item["temporal_role"] for item in data["items"]] == [
        "candidate_recent",
        "annual_historical",
    ]
    historical = data["items"][1]
    assert historical["occurred_at"] == "2025-02-01T00:00:00Z"
    assert historical["ended_at"] == historical["occurred_at"]
    assert historical["coverage_end"] == "2025-06-01T00:00:00Z"
    assert historical["reported_fatalities_low"] == 1
    assert historical["reported_fatalities_high"] == 4
    assert historical["provenance"]["version"] == "test-1"
    assert client.get(f"{PREFIX}/ucdp-observations?country=RS").json()["items"] == []
    selected = client.get(f"{PREFIX}/ucdp-observations?end=2025-07-01").json()["items"]
    assert [item["temporal_role"] for item in selected] == ["annual_historical"]


def test_forecast_temporal_consistency_indicators_and_provenance(client, records):
    response = client.get(f"{PREFIX}/forecasts?country=ES&start=2025-05-01&end=2025-06-01")
    assert response.status_code == 200
    result = Page[Prediction].model_validate(response.json())
    (forecast,) = result.items
    assert forecast.issued_at == moment(5)
    assert forecast.target_start == moment(7)
    assert forecast.target_end == moment(9)
    assert forecast.target_period_status == "active"
    assert forecast.horizon_months == 3
    assert forecast.unit == "native event count"
    assert forecast.provenance.analysis_run_id == records
    assert forecast.provenance.version == "test-1"
    assert forecast.provenance.retrieved_at == moment(6)
    assert "private" not in response.text
    assert client.get(f"{PREFIX}/forecasts?start=2025-07-01").json()["items"] == []
    global_forecasts = client.get(f"{PREFIX}/forecasts").json()["items"]
    subnational = next(item for item in global_forecasts if item["geography"]["unit"] == "admin1")
    assert subnational["geography"]["iso3"] is None
    indicators = client.get(f"{PREFIX}/indicators?country=ES").json()["items"]
    assert [item["value"] for item in indicators] == [None, 3.0]
    assert indicators[0]["kind"] == "derived_indicator"
    overview_response = client.get(f"{PREFIX}/overview?country=ESP")
    overview = Overview.model_validate(overview_response.json())
    assert overview.assessment.probability_low is None
    assert overview.assessment.probability_high is None
    assert overview.assessment.issued_at == moment(6)
    assert overview.assessment.provenance.version == "synthetic-v1"
    assert overview.observation.provenance.source_record_id == "synthetic-event-1"
    assert "private" not in overview_response.text
    assert (
        client.get(f"{PREFIX}/coverage?country=ESP").json() == overview_response.json()["coverage"]
    )


def test_database_unavailable():
    def unavailable():
        raise OperationalError(None, None, RuntimeError("private connection details"))

    engine = create_engine("sqlite://", creator=unavailable)

    def broken_session():
        with Session(engine) as session:
            yield session

    dashboard_app.dependency_overrides[get_session] = broken_session
    try:
        with TestClient(dashboard_app) as client:
            for endpoint in ("observations", "overview", "coverage"):
                response = client.get(f"{PREFIX}/{endpoint}")
                assert response.status_code == 503
                assert response.json() == {"detail": "Dashboard database unavailable"}
    finally:
        dashboard_app.dependency_overrides.pop(get_session)
        engine.dispose()


def test_dashboard_app_hides_internal_routes_for_unauthenticated_clients():
    with TestClient(dashboard_app) as client:
        assert client.post("/analysis", json={}).status_code == 404
        assert client.get(f"/analysis/{UUID(int=1)}").status_code == 404
        for path in ("/providers", "/forecasts", f"/forecasts/{UUID(int=1)}"):
            assert client.get(path).status_code == 404
        assert client.post(f"{PREFIX}/observations", json={}).status_code == 405
        paths = client.get("/openapi.json").json()["paths"]
        assert all(path.startswith(PREFIX) for path in paths)
        assert "200" in paths[f"{PREFIX}/observations"]["get"]["responses"]


def test_overview_reads_each_series_once(client, session):
    queries = []

    def count_query(*args):
        queries.append(args[2])

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", count_query)
    try:
        assert client.get(f"{PREFIX}/overview").status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", count_query)
    assert len(queries) == 5
    assert all("LIMIT" in query for query in queries)
