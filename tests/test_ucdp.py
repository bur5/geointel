import httpx
import pytest

from geointel.connectors.ucdp import UCDPConnector, UCDPError

RECORD = {
    "id": 7,
    "country": "Spain",
    "date_start": "2024-01-02T00:00:00Z",
    "deaths_best": 0,
    "type_of_violence": 1,
}


def test_normalization_preserves_provenance():
    connector = UCDPConnector("https://example.test", "24.1")
    item = connector.normalize(RECORD, "Spain", "https://example.test/events?country=Spain")
    assert item.source_record_id == "7"
    assert item.provenance["dataset_version"] == "24.1"
    assert item.provenance["record_id"] == "7"
    assert item.provenance["retrieval_url"].startswith("https://example.test/events")


def test_transient_failure_retries_then_succeeds():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, request=request)
        return httpx.Response(200, json={"Result": [RECORD]}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = UCDPConnector(
        "https://example.test", "24.1", "events", retries=2, client=client, sleep=lambda _: None
    ).collect("Spain")
    assert calls == 2
    assert result[0].source_record_id == "7"
    client.close()


def test_network_failure_is_explicit_and_bounded():
    calls = 0

    def fail(request):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline", request=request)

    client = httpx.Client(transport=httpx.MockTransport(fail))
    with pytest.raises(UCDPError, match="2 attempts"):
        UCDPConnector(
            "https://example.test",
            "24.1",
            "events",
            retries=1,
            client=client,
            sleep=lambda _: None,
        ).collect("Spain")
    assert calls == 2
    client.close()


def test_permanent_4xx_is_not_retried():
    calls = 0

    def reject(request):
        nonlocal calls
        calls += 1
        return httpx.Response(404, request=request)

    client = httpx.Client(transport=httpx.MockTransport(reject))
    with pytest.raises(UCDPError, match="1 attempts"):
        UCDPConnector("https://example.test", "24.1", "events", retries=3, client=client).collect(
            "Spain"
        )
    assert calls == 1
    client.close()


@pytest.mark.parametrize("payload", [[], {}, {"Result": {}}, {"Result": [], "results": []}])
def test_invalid_response_envelope_is_rejected_without_retry(payload):
    calls = 0

    def invalid(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=payload, request=request)

    client = httpx.Client(transport=httpx.MockTransport(invalid))
    with pytest.raises(UCDPError, match="1 attempts"):
        UCDPConnector("https://example.test", "24.1", "events", retries=2, client=client).collect(
            "Spain"
        )
    assert calls == 1
    client.close()


def test_injected_client_remains_caller_owned():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"results": []}, request=request)
        )
    )
    connector = UCDPConnector("https://example.test", "24.1", "events", client=client)
    assert connector.collect("Spain") == []
    assert not client.is_closed
    client.close()


def test_configuration_validation():
    with pytest.raises(ValueError, match="timeout"):
        UCDPConnector("https://example.test", "24.1", timeout=0)
    with pytest.raises(ValueError, match="retries"):
        UCDPConnector("https://example.test", "24.1", retries=-1)


def test_unconfigured_endpoint_is_not_invented():
    with pytest.raises(UCDPError, match="not configured"):
        UCDPConnector("https://example.test", "24.1").collect("Spain")
