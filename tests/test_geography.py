import httpx
import pytest

from geointel.connectors.ucdp import UCDPConnector, UCDPError
from geointel.geography import resolve_country
from geointel.providers.runtime import FailureCategory


@pytest.mark.parametrize(
    "name,code",
    [("Spain", 230), ("Georgia", 372), ("Taiwan", 713), ("Serbia", 340), ("Nigeria", 475)],
)
def test_validation_country_gw_resolution(name, code):
    assert resolve_country(name).gw_code == code


def test_unknown_country_fails_before_any_request():
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request)))
    connector = UCDPConnector(
        "https://ucdpapi.pcr.uu.se/api",
        "26.1",
        access_token="fake-test-token",
        official_api=True,
        client=client,
    )
    with pytest.raises(UCDPError) as error:
        connector.collect("Unknownland")
    assert error.value.category == FailureCategory.CONFIGURATION_ERROR
    assert calls == []
    assert connector.last_audit is None
    client.close()


def test_annual_and_candidate_provenance_are_distinct():
    raw = {"id": 1, "country": "Spain", "country_id": 230, "best": 3, "low": 2, "high": 4}
    annual = UCDPConnector("https://example.test", "26.1")
    candidate = UCDPConnector("https://example.test", "26.0.8", dataset_role="candidate_recent")
    assert annual.normalize(raw, "Spain").provenance["temporal_role"] == "annual_historical"
    item = candidate.normalize(raw, "Spain")
    assert item.provenance["temporal_role"] == "candidate_recent"
    assert item.provenance["not_realtime"] is True
