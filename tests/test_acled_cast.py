from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import ValidationError
from test_api_pipeline import REQUEST
from test_views import SYNTHETIC_RECORD

from geointel.config import Settings
from geointel.connectors.acled import ACLEDConnector, ACLEDError
from geointel.connectors.cast import CASTConnector, CASTError
from geointel.domain.models import Event, Evidence, ForecastSignal

ACLED_RECORD = {
    "event_id": "synthetic-acled-1",
    "event_date": datetime.now(UTC).isoformat(),
    "event_type": "Protests",
    "sub_event_type": "Peaceful protest",
    "country": "Spain",
    "admin1": "Madrid",
    "location": "Madrid",
    "latitude": 40.4,
    "longitude": -3.7,
    "actor1": "Synthetic test actor",
    "fatalities": 0,
    "notes": "Synthetic fixture only",
    "source": "Synthetic fixture",
    "source_scale": "Other",
    "disorder_type": "Political violence",
}


def test_configuration_validation_and_disabled_defaults(monkeypatch):
    # Exercise defaults and constructor overrides without developer environment or dotenv settings.
    monkeypatch.setattr(
        Settings,
        "settings_customise_sources",
        staticmethod(lambda settings_cls, init_settings, **sources: (init_settings,)),
    )
    defaults = Settings()
    assert not defaults.acled_enabled and not defaults.cast_enabled
    with pytest.raises(ValidationError, match="ACLED_BASE_URL"):
        Settings(acled_enabled=True)
    with pytest.raises(ValidationError, match="CAST_BASE_URL"):
        Settings(cast_enabled=True)
    with pytest.raises(ValueError, match="timeout"):
        ACLEDConnector("https://example.test", "events", timeout=0)
    with pytest.raises(ValueError, match="retries"):
        CASTConnector("https://example.test", "forecasts", retries=-1)


def test_unconfigured_endpoints_are_not_invented():
    with pytest.raises(ACLEDError, match="verified adapter"):
        ACLEDConnector("", None).collect("Spain")
    with pytest.raises(CASTError, match="verified adapter"):
        CASTConnector("", None).collect("Spain")


def test_acled_normalization_provenance_and_temporal_alignment():
    event = ACLEDConnector("https://example.test", "events").normalize(
        ACLED_RECORD, "Spain", "https://example.test/events?location=Spain"
    )
    assert event.provider == "ACLED" and event.source_record_id == "synthetic-acled-1"
    assert event.temporal_classification == "current_window"
    assert event.provenance["observed_report_not_prediction"] is True
    assert event.provenance["fatalities_are_reported_not_precise"] is True
    stale = {**ACLED_RECORD, "event_date": (datetime.now(UTC) - timedelta(days=91)).isoformat()}
    assert "stale event" in ACLEDConnector("x", "y").normalize(stale, "Spain").alignment_notes[0]


def test_acled_exact_duplicates_are_deduplicated_and_retry_is_bounded():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"events": [ACLED_RECORD, ACLED_RECORD]}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = ACLEDConnector(
        "https://example.test", "events", retries=1, client=client, sleep=lambda _: None
    )
    result = connector.collect("Spain")
    assert calls == 2 and len(result) == 1
    assert connector.last_audit.duplicates == 1
    client.close()


@pytest.mark.parametrize(
    "connector,error,envelope",
    [
        (ACLEDConnector, ACLEDError, {"events": []}),
        (CASTConnector, CASTError, {"forecasts": []}),
    ],
)
def test_permanent_and_malformed_failures(connector, error, envelope):
    calls = 0

    def reject(request):
        nonlocal calls
        calls += 1
        return httpx.Response(403, request=request)

    client = httpx.Client(transport=httpx.MockTransport(reject))
    with pytest.raises(error):
        connector("https://example.test", next(iter(envelope)), retries=3, client=client).collect(
            "Spain"
        )
    assert calls == 1
    client.close()
    bad = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}, request=request))
    )
    with pytest.raises(error):
        connector("https://example.test", next(iter(envelope)), client=bad).collect("Spain")
    bad.close()


def test_cast_normalizes_as_predictive_signal_not_event():
    signal = CASTConnector("https://example.test", "forecasts").normalize(
        SYNTHETIC_RECORD, "Spain", 12, "https://example.test/forecasts?location=Spain"
    )
    assert signal.provider == "CAST"
    assert signal.provenance["schema"] == "geointel-cast-adapter-v1"
    assert signal.provenance["predictive_not_observed"] is True
    assert "probability" not in signal.model_dump()


def test_cast_transient_retry_uses_predictive_adapter_contract():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, request=request)
        return httpx.Response(200, json={"forecasts": [SYNTHETIC_RECORD]}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    signals = CASTConnector(
        "https://example.test",
        "forecasts",
        retries=1,
        client=client,
        sleep=lambda _: None,
    ).collect("Spain", 12)
    assert calls == 2 and signals[0].provider == "CAST"
    client.close()


class ACLEDRecords:
    connector_name = "ACLED"

    def collect(self, location, horizon_months):
        connector = ACLEDConnector("https://example.test", "events")
        item = connector.normalize(ACLED_RECORD, location)
        return [item, item]


class CASTRecords:
    connector_name = "CAST"

    def collect(self, location, horizon_months):
        return [
            CASTConnector("https://example.test", "forecasts").normalize(
                SYNTHETIC_RECORD, location, horizon_months
            )
        ]


def test_pipeline_separates_acled_events_and_cast_signals(client, session, monkeypatch):
    monkeypatch.setattr("geointel.api.app.connectors", lambda: [ACLEDRecords(), CASTRecords()])
    response = client.post("/analysis", json=REQUEST)
    assert response.status_code == 201
    metadata = response.json()["collection_metadata"]
    assert metadata["recent_event_count"] == 1
    assert metadata["forecast_signal_count"] == 1
    assert [item["record_count"] for item in metadata["connector_outcomes"]] == [1, 1]
    assert [item["duplicates_removed"] for item in metadata["connector_outcomes"]] == [1, 0]
    assert session.query(Event).count() == 1
    assert session.query(ForecastSignal).count() == 1
    assert session.query(Evidence).count() == 0
    analyst = response.json()["analyst_output"]
    assert analyst["recent_events"] and analyst["predictive_signals"]
    assert all(row.provider == "CAST" for row in session.query(ForecastSignal))


def test_acled_and_cast_outages_are_isolated(client, monkeypatch):
    class Failed:
        def __init__(self, name):
            self.connector_name = name

        def collect(self, location, horizon_months):
            raise RuntimeError("upstream unavailable")

    monkeypatch.setattr("geointel.api.app.connectors", lambda: [CASTRecords(), Failed("ACLED")])
    response = client.post("/analysis", json=REQUEST)
    assert response.status_code == 201
    assert [x["status"] for x in response.json()["collection_metadata"]["connector_outcomes"]] == [
        "succeeded",
        "failed",
    ]
