import httpx, pytest
from geointel.connectors.ucdp import UCDPConnector,UCDPError
def test_normalization():
    connector=UCDPConnector("https://example.test","24.1")
    item=connector.normalize({"id":7,"country":"Spain","date_start":"2024-01-02T00:00:00Z","deaths_best":0,"type_of_violence":1},"Spain")
    assert item.source_record_id=="7" and item.provenance["dataset_version"]=="24.1"
def test_failure_is_explicit_and_bounded():
    def fail(request): raise httpx.ConnectError("offline",request=request)
    client=httpx.Client(transport=httpx.MockTransport(fail))
    with pytest.raises(UCDPError,match="2 attempts"):
        UCDPConnector("https://example.test","24.1","events",retries=1,client=client).collect("Spain")
def test_unconfigured_endpoint_is_not_invented():
    with pytest.raises(UCDPError,match="not configured"): UCDPConnector("https://example.test","24.1").collect("Spain")
