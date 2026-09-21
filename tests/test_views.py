from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

from geointel.config import Settings
from geointel.connectors.views import VIEWSConnector, VIEWSError

SYNTHETIC_RECORD = {
    "id": "synthetic-spain-001",
    "model": "synthetic-test-model",
    "model_version": "test-1",
    "geographic_unit": "country",
    "location": "Spain",
    "issue_date": "2026-01-01T00:00:00Z",
    "target_start": "2026-02-01T00:00:00Z",
    "target_end": "2027-01-31T00:00:00Z",
    "horizon_months": 12,
    "target_variable": "synthetic_test_target",
    "prediction": 2.5,
    "unit": "provider_native_units",
    "scale": "synthetic; semantics intentionally unspecified",
}


def test_views_configuration_validation():
    with pytest.raises(ValidationError, match="VIEWS_BASE_URL"):
        Settings(views_enabled=True)
    with pytest.raises(ValueError, match="timeout"):
        VIEWSConnector("https://example.test", "forecast", timeout=0)
    with pytest.raises(ValueError, match="retries"):
        VIEWSConnector("https://example.test", "forecast", retries=-1)


def test_unconfigured_endpoint_is_not_invented():
    with pytest.raises(VIEWSError, match="verified adapter endpoint"):
        VIEWSConnector("", None).collect("Spain", 12)


def test_normalization_retains_predictive_provenance_without_probability_semantics():
    signal = VIEWSConnector("https://example.test", "forecasts").normalize(
        SYNTHETIC_RECORD, "Spain", 12, "https://example.test/forecasts?location=Spain"
    )
    assert signal.provider == "VIEWS"
    assert signal.prediction == 2.5
    assert signal.unit == "provider_native_units"
    assert signal.provenance["predictive_not_observed"] is True
    assert signal.provenance["schema"] == "geointel-views-adapter-v1"
    assert signal.provenance["raw_adapter_record"]["prediction"] == 2.5
    assert "probability" not in signal.model_dump()
    assert signal.alignment_status == "aligned"
    assert signal.retrieved_at <= datetime.now(UTC)


def test_geographic_and_horizon_mismatch_are_surfaced_without_aggregation():
    raw = {**SYNTHETIC_RECORD, "geographic_unit": "grid", "horizon_months": 1}
    signal = VIEWSConnector("https://example.test", "forecasts").normalize(raw, "Spain", 12)
    assert signal.alignment_status == "mismatch"
    assert any("geographic mismatch" in note for note in signal.alignment_notes)
    assert any("horizon mismatch" in note for note in signal.alignment_notes)
    assert signal.prediction == raw["prediction"]


def test_successful_collection_and_transient_retry():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"forecasts": [SYNTHETIC_RECORD]}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = VIEWSConnector(
        "https://example.test", "forecasts", retries=1, client=client, sleep=lambda _: None
    )
    signals = connector.collect("Spain", 12)
    assert calls == 2
    assert signals[0].source_record_id == "synthetic-spain-001"
    client.close()


def test_permanent_failure_is_not_retried():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(403, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(VIEWSError, match="1 attempts"):
        VIEWSConnector("https://example.test", "forecasts", retries=3, client=client).collect(
            "Spain", 12
        )
    assert calls == 1
    client.close()


@pytest.mark.parametrize(
    "payload", [[], {}, {"forecasts": {}}, {"forecasts": [], "unexpected": []}]
)
def test_malformed_payload_is_rejected(payload):
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload, request=request)
        )
    )
    with pytest.raises(VIEWSError, match="1 attempts"):
        VIEWSConnector("https://example.test", "forecasts", client=client).collect("Spain", 12)
    client.close()
