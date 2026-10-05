from test_api_pipeline import REQUEST
from test_views import SYNTHETIC_RECORD

from geointel.connectors.views import VIEWSConnector
from geointel.domain.models import Event, Evidence, Forecast, ForecastSignal
from geointel.domain.schemas import Confidence, NormalizedEvidence


class SuccessfulUCDP:
    connector_name = "UCDP"

    def collect(self, location, horizon_months):
        from datetime import UTC, datetime

        return [
            NormalizedEvidence(
                source_name="UCDP",
                source_record_id="observed-1",
                title="Synthetic observed fixture",
                summary="Explicitly synthetic historical test evidence.",
                retrieved_at=datetime.now(UTC),
                geographic_scope=location,
                reliability=Confidence.HIGH,
                provenance={"synthetic_fixture": True, "temporal_role": "annual_historical"},
            )
        ]


class SuccessfulVIEWS:
    connector_name = "VIEWS"

    def collect(self, location, horizon_months):
        return [
            VIEWSConnector("https://example.test", "forecasts").normalize(
                SYNTHETIC_RECORD, location, horizon_months, "https://example.test/forecasts"
            )
        ]


class Failed:
    def __init__(self, name):
        self.connector_name = name

    def collect(self, location, horizon_months):
        raise RuntimeError(f"{self.connector_name} unavailable")


def test_views_signal_is_persisted_separately_and_never_becomes_event(client, session, monkeypatch):
    monkeypatch.setattr(
        "geointel.api.app.connectors", lambda: [SuccessfulUCDP(), SuccessfulVIEWS()]
    )
    response = client.post("/analysis", json=REQUEST)
    assert response.status_code == 201
    metadata = response.json()["collection_metadata"]
    assert metadata["evidence_count"] == 1
    assert metadata["forecast_signal_count"] == 1
    assert all(item["succeeded"] for item in metadata["connector_outcomes"])
    assert session.query(Evidence).count() == 1
    assert session.query(ForecastSignal).count() == 1
    assert session.query(Event).count() == 0
    assert all(item.probability_low is None for item in session.query(Forecast).all())
    analyst = response.json()["analyst_output"]
    assert analyst["observed_evidence"] == []
    assert analyst["historical_evidence"]
    assert analyst["predictive_signals"]


def test_connector_failures_are_isolated_in_every_combination(client, monkeypatch):
    combinations = [
        [SuccessfulUCDP(), Failed("VIEWS")],
        [Failed("UCDP"), SuccessfulVIEWS()],
        [Failed("UCDP"), Failed("VIEWS")],
    ]
    for connectors in combinations:
        monkeypatch.setattr("geointel.api.app.connectors", lambda c=connectors: c)
        response = client.post("/analysis", json=REQUEST)
        assert response.status_code == 201
        outcomes = response.json()["collection_metadata"]["connector_outcomes"]
        assert len(outcomes) == 2
        assert [item["status"] for item in outcomes] == [
            "succeeded" if not isinstance(item, Failed) else "failed" for item in connectors
        ]
