from datetime import date, timedelta

import httpx
import pytest

from geointel.connectors.acled import ACLEDConnector
from geointel.connectors.cast import CASTConnector, CASTError
from geointel.connectors.ucdp import UCDPConnector, UCDPError
from geointel.domain.schemas import NormalizedForecastSignal, NormalizedOperationalEvent
from geointel.providers.acled_auth import ACLEDAuthError, ACLEDOAuthClient
from geointel.providers.runtime import CollectionStatus, FailureCategory, HardenedTransport


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def token_payload(access="test-access", refresh="test-refresh", expires=86400):
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": expires,
        "refresh_expires_in": 1209600,
    }


def ucdp_record(identity=7):
    return {
        "id": identity,
        "country": "Spain",
        "date_start": "2024-01-02T00:00:00Z",
        "type_of_violence": 1,
        "deaths_best": 2,
        "deaths_low": 1,
        "deaths_high": 3,
        "latitude": 40.4,
        "longitude": -3.7,
    }


def test_ucdp_official_header_version_pagination_duplicate_and_provenance():
    requests = []

    def handler(request):
        requests.append(request)
        page = request.url.params["page"]
        rows = [ucdp_record(7)] if page == "1" else [ucdp_record(7), ucdp_record(8)]
        return httpx.Response(
            200,
            json={
                "TotalCount": 3,
                "TotalPages": 2,
                "PreviousPageUrl": None,
                "NextPageUrl": None,
                "Result": rows,
            },
            request=request,
        )

    client = mock_client(handler)
    connector = UCDPConnector(
        "https://ucdpapi.pcr.uu.se/api",
        "26.1",
        access_token="ucdp-test-secret",
        official_api=True,
        client=client,
        retries=0,
    )
    records = connector.collect("Spain")
    assert [row.source_record_id for row in records] == ["7", "8"]
    assert (
        connector.last_audit.duplicates == 1
        and connector.last_audit.status == CollectionStatus.SUCCEEDED
    )
    assert all(request.headers["x-ucdp-access-token"] == "ucdp-test-secret" for request in requests)
    assert all(request.url.path.endswith("/gedevents/26.1") for request in requests)
    rendered = str([row.provenance for row in records])
    assert "ucdp-test-secret" not in rendered and records[0].provenance["dataset_version"] == "26.1"
    assert records[0].provenance["observed_historical_not_forecast"] is True
    client.close()


@pytest.mark.parametrize("pages", ["2", 1.5, None, True])
def test_ucdp_rejects_malformed_total_pages(pages):
    client = mock_client(
        lambda request: httpx.Response(
            200, json={"TotalPages": pages, "Result": []}, request=request
        )
    )
    connector = UCDPConnector(
        "https://ucdpapi.pcr.uu.se/api",
        "26.1",
        access_token="secret",
        official_api=True,
        client=client,
        retries=0,
    )
    with pytest.raises(UCDPError) as found:
        connector.collect("Spain")
    assert found.value.category == FailureCategory.PAGINATION_ERROR
    client.close()


@pytest.mark.parametrize(
    "status,category",
    [(401, FailureCategory.AUTHENTICATION_ERROR), (429, FailureCategory.RATE_LIMITED)],
)
def test_ucdp_official_classifies_auth_and_quota_without_leaking_token(status, category):
    client = mock_client(
        lambda request: httpx.Response(status, text="token=provider-secret", request=request)
    )
    connector = UCDPConnector(
        "https://ucdpapi.pcr.uu.se/api",
        "26.1",
        access_token="ucdp-secret",
        official_api=True,
        client=client,
        retries=0,
    )
    with pytest.raises(UCDPError) as found:
        connector.collect("Spain")
    assert found.value.category == category and "ucdp-secret" not in str(found.value)
    assert "provider-secret" not in str(found.value)
    client.close()


def test_acled_oauth_success_cache_refresh_failure_and_secret_safety():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=token_payload(
                access=f"access-{len(calls)}", expires=1 if len(calls) == 1 else 86400
            ),
            request=request,
        )

    client = mock_client(handler)
    auth = ACLEDOAuthClient(
        "person@example.test", "password-secret", HardenedTransport(client=client, retries=0)
    )
    assert auth.access_token() == "access-1"
    assert auth.access_token() == "access-2"  # first token is inside the 60-second refresh window
    assert auth.access_token() == "access-2"
    assert len(calls) == 2 and b"refresh_token=test-refresh" in calls[1].content
    assert "password-secret" not in str(auth.safe_status()) and "access-2" not in str(
        auth.safe_status()
    )
    client.close()
    bad = mock_client(
        lambda request: httpx.Response(401, text="password=password-secret", request=request)
    )
    with pytest.raises(ACLEDAuthError) as found:
        ACLEDOAuthClient(
            "user", "password-secret", HardenedTransport(client=bad, retries=0)
        ).access_token()
    assert (
        found.value.category == FailureCategory.AUTHENTICATION_ERROR
        and "password-secret" not in str(found.value)
    )
    bad.close()


def acled_event(identity):
    return {
        "event_id_cnty": identity,
        "event_date": "1 January 2024",
        "event_type": "Battles",
        "sub_event_type": "Armed clash",
        "country": "Spain",
        "admin1": "Madrid",
        "location": "Madrid",
        "latitude": 40.4,
        "longitude": -3.7,
        "actor1": "Actor A",
        "fatalities": 4,
        "source": "Test source",
    }


def oauth_and_transport(handler):
    client = mock_client(handler)
    transport = HardenedTransport(client=client, retries=0)
    auth = ACLEDOAuthClient("user", "password", transport)
    return client, transport, auth


def test_acled_official_cursor_event_identity_fatalities_duplicate_and_bearer_secrecy():
    event_requests = []

    def handler(request):
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=token_payload(), request=request)
        event_requests.append(request)
        cursor = request.url.params["cursor"]
        payload = (
            {"data": [acled_event("ESP1"), acled_event("ESP1")], "next_cursor": "next"}
            if cursor == "0"
            else {"data": [acled_event("ESP2")], "next_cursor": None}
        )
        return httpx.Response(200, json=payload, request=request)

    client, transport, auth = oauth_and_transport(handler)
    connector = ACLEDConnector(
        "https://acleddata.com/api", None, official_api=True, oauth=auth, transport=transport
    )
    records = connector.collect("Spain")
    assert all(isinstance(row, NormalizedOperationalEvent) for row in records)
    assert [row.source_record_id for row in records] == ["ESP1", "ESP2"] and records[
        0
    ].fatalities == 4
    assert connector.last_audit.duplicates == 1
    assert [request.url.params["cursor"] for request in event_requests] == ["0", "next"]
    assert all(request.url.params["event_date_where"] == "BETWEEN" for request in event_requests)
    for request in event_requests:
        start_text, end_text = request.url.params["event_date"].split("|")
        start, end = date.fromisoformat(start_text), date.fromisoformat(end_text)
        assert end - start == timedelta(days=90)
        assert end == date.today()
    assert all(
        request.headers["authorization"] == "Bearer test-access" for request in event_requests
    )
    assert "test-access" not in str([row.provenance for row in records])
    assert records[0].provenance["fatalities_are_reported_not_precise"] is True
    assert records[0].provenance["operational_window_days"] == 90
    client.close()


def test_acled_repeated_cursor_partial_failure_and_malformed_event():
    count = 0

    def handler(request):
        nonlocal count
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=token_payload(), request=request)
        count += 1
        if count == 1:
            return httpx.Response(
                200, json={"data": [acled_event("ESP1")], "next_cursor": "again"}, request=request
            )
        return httpx.Response(
            200,
            json={"data": [acled_event("ESP2"), {"event_id_cnty": "bad"}], "next_cursor": "again"},
            request=request,
        )

    client, transport, auth = oauth_and_transport(handler)
    connector = ACLEDConnector(
        "https://acleddata.com/api", None, official_api=True, oauth=auth, transport=transport
    )
    records = connector.collect("Spain")
    assert [row.source_record_id for row in records] == ["ESP1", "ESP2"]
    assert connector.last_audit.status == CollectionStatus.PARTIAL
    assert connector.last_audit.failure_category == FailureCategory.PAGINATION_ERROR
    assert connector.last_audit.rejected == 1
    client.close()


def cast_row():
    return {
        "country": "Spain",
        "admin1": "Madrid",
        "month": "October",
        "year": 2026,
        "total_forecast": 8,
        "battles_forecast": 4,
        "erv_forecast": 2,
        "vac_forecast": 1,
        "total_observed": 6,
        "battles_observed": 3,
        "erv_observed": 1,
        "vac_observed": 2,
        "timestamp": 1789430400,
    }


def test_cast_official_normalizes_four_event_count_signals_never_events():
    def handler(request):
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=token_payload(), request=request)
        assert request.url.path == "/api/cast/read"
        assert request.url.params["country"] == "Spain"
        return httpx.Response(
            200, json={"data": [cast_row()], "next_cursor": None}, request=request
        )

    client, transport, auth = oauth_and_transport(handler)
    connector = CASTConnector(
        "https://acleddata.com/api", None, official_api=True, oauth=auth, transport=transport
    )
    records = connector.collect("Spain", 6)
    assert len(records) == 4 and all(isinstance(row, NormalizedForecastSignal) for row in records)
    assert {row.target_variable for row in records} == {
        "total_events",
        "battles",
        "explosions_remote_violence",
        "violence_against_civilians",
    }
    battle = next(row for row in records if row.target_variable == "battles")
    assert battle.prediction == 4 and battle.unit == "forecast_event_count"
    assert battle.provenance["observed_context"]["battles"] == 3
    assert battle.provenance["forecast_and_observed_are_distinct"] is True
    assert battle.target_start.month == 10
    assert battle.issue_date.tzinfo is not None
    assert "probability" not in battle.model_dump() and not isinstance(
        battle, NormalizedOperationalEvent
    )
    client.close()


def test_cast_auth_failure_and_partial_collection():
    bad = mock_client(lambda request: httpx.Response(401, request=request))
    transport = HardenedTransport(client=bad, retries=0)
    connector = CASTConnector(
        "https://acleddata.com/api",
        None,
        official_api=True,
        oauth=ACLEDOAuthClient("u", "p", transport),
        transport=transport,
    )
    with pytest.raises(CASTError):
        connector.collect("Spain")
    bad.close()

    calls = 0

    def handler(request):
        nonlocal calls
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=token_payload(), request=request)
        calls += 1
        if calls == 1:
            return httpx.Response(
                200, json={"data": [cast_row()], "next_cursor": "two"}, request=request
            )
        return httpx.Response(503, request=request)

    client, transport, auth = oauth_and_transport(handler)
    connector = CASTConnector(
        "https://acleddata.com/api", None, official_api=True, oauth=auth, transport=transport
    )
    assert len(connector.collect("Spain")) == 4
    assert connector.last_audit.status == CollectionStatus.PARTIAL
    assert connector.last_audit.failure_category == FailureCategory.PROVIDER_5XX
    client.close()


def test_acled_empty_recency_restricted_response_is_not_successful_coverage():
    def handler(request):
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=token_payload(), request=request)
        return httpx.Response(
            200,
            json={
                "data": [],
                "next_cursor": None,
                "data_query_restrictions": {"data_recency": "12 months"},
            },
            request=request,
        )

    client, transport, auth = oauth_and_transport(handler)
    connector = ACLEDConnector(
        "https://acleddata.com/api", None, official_api=True, oauth=auth, transport=transport
    )
    assert connector.collect("Spain") == []
    assert connector.last_audit.status == CollectionStatus.PARTIAL
    assert connector.last_audit.failure_category == FailureCategory.RECENCY_RESTRICTED
    assert connector.last_audit.provider_restrictions == {"data_recency": "12 months"}
    assert "absence of events" in connector.last_audit.failure_reason
    client.close()


def test_acled_empty_unrestricted_response_remains_successful_empty_collection():
    def handler(request):
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=token_payload(), request=request)
        return httpx.Response(
            200,
            json={"data": [], "next_cursor": None, "data_query_restrictions": {}},
            request=request,
        )

    client, transport, auth = oauth_and_transport(handler)
    connector = ACLEDConnector(
        "https://acleddata.com/api", None, official_api=True, oauth=auth, transport=transport
    )
    assert connector.collect("Spain") == []
    assert connector.last_audit.status == CollectionStatus.SUCCEEDED
    assert connector.last_audit.failure_category is None
    client.close()
