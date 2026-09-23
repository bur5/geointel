import json
from importlib import import_module

import httpx
import pytest

from geointel.config import Settings
from geointel.providers.registry import public_capabilities
from geointel.providers.runtime import (
    CollectionAudit,
    CollectionStatus,
    FailureCategory,
    HardenedTransport,
    IntegrationMode,
    TransportError,
    paginate,
    sanitize_mapping,
    sanitize_text,
    sanitize_url,
    validate_provider_url,
)


def audit():
    return CollectionAudit("TEST", "0.1.1", IntegrationMode.FIXTURE, "test-v1")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://example.test",
        "https://user:pass@example.test",
        "https://localhost/x",
        "https://127.0.0.1/x",
        "https://169.254.169.254/latest",
        "https://10.0.0.1/x",
        "not a url",
    ],
)
def test_unsafe_urls_are_rejected(url):
    with pytest.raises(ValueError):
        validate_provider_url(url)


def test_private_adapter_requires_explicit_opt_in():
    assert validate_provider_url("https://10.0.0.1/adapter", allow_private=True)
    with pytest.raises(ValueError, match="unsafe ACLED"):
        Settings(acled_enabled=True, acled_base_url="https://127.0.0.1", acled_endpoint_path="x")
    assert Settings(
        acled_enabled=True,
        acled_base_url="https://10.0.0.1",
        acled_endpoint_path="x",
        provider_allow_private_networks=True,
    )


def test_secret_sanitization_is_recursive_bounded_and_url_safe():
    url = sanitize_url(
        "https://example.test/x?country=Spain&api_key=very-secret&token=also-secret#fragment"
    )
    assert (
        "very-secret" not in url
        and "also-secret" not in url
        and "Spain" in url
        and not url.endswith("fragment")
    )
    value = sanitize_mapping(
        {"Authorization": "Bearer abc", "nested": {"cookie": "yum", "ok": "Bearer xyz"}}
    )
    rendered = json.dumps(value)
    assert "abc" not in rendered and "yum" not in rendered and "xyz" not in rendered
    assert "secret-token" not in sanitize_text("token=secret-token")


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_transport_retries_429_then_succeeds_and_sanitizes_provenance_url():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    owned = client(handler)
    payload, url, attempts = HardenedTransport(client=owned, sleep=lambda _: None).get_json(
        "https://example.test/data", params={"api_key": "secret", "country": "Spain"}
    )
    assert payload == {"ok": True} and attempts == 2 and calls == 2
    assert "secret" not in url and "Spain" in url
    owned.close()


@pytest.mark.parametrize(
    "status,category,calls",
    [
        (401, FailureCategory.AUTHENTICATION_ERROR, 1),
        (403, FailureCategory.AUTHORIZATION_ERROR, 1),
        (429, FailureCategory.RATE_LIMITED, 2),
        (503, FailureCategory.PROVIDER_5XX, 2),
    ],
)
def test_transport_failure_taxonomy_and_bounded_retries(status, category, calls):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(status, request=request)

    owned = client(handler)
    with pytest.raises(TransportError) as found:
        HardenedTransport(retries=1, client=owned, sleep=lambda _: None).get_json(
            "https://example.test/x"
        )
    assert found.value.category == category and count == calls
    owned.close()


def test_transport_timeout_oversize_content_type_and_redirect():
    cases = [
        (
            lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("token=bad", request=request)),
            FailureCategory.TIMEOUT,
            {},
        ),
        (
            lambda request: httpx.Response(200, content=b"12345", request=request),
            FailureCategory.PAYLOAD_TOO_LARGE,
            {"max_bytes": 4},
        ),
        (
            lambda request: httpx.Response(
                200, text="hello", headers={"content-type": "text/plain"}, request=request
            ),
            FailureCategory.INVALID_RESPONSE,
            {},
        ),
        (
            lambda request: httpx.Response(
                302, headers={"location": "http://127.0.0.1"}, request=request
            ),
            FailureCategory.INVALID_RESPONSE,
            {},
        ),
    ]
    for handler, category, kwargs in cases:
        owned = client(handler)
        with pytest.raises(TransportError) as found:
            HardenedTransport(retries=0, client=owned, **kwargs).get_json("https://example.test/x")
        assert found.value.category == category and "bad" not in str(found.value)
        owned.close()


def test_pagination_deduplicates_stops_empty_and_repeated_cursor():
    pages = {None: ([{"id": "1"}, {"id": "1"}], "two"), "two": ([{"id": "2"}], "two")}
    result_audit = audit()
    result = paginate(
        lambda cursor: pages[cursor], identity=lambda row: row["id"], audit=result_audit
    )
    assert [x["id"] for x in result] == ["1", "2"]
    assert result_audit.duplicates == 1 and result_audit.status == CollectionStatus.PARTIAL
    assert result_audit.failure_category == FailureCategory.PAGINATION_ERROR
    empty_audit = audit()
    assert paginate(lambda _: ([], None), identity=lambda row: row["id"], audit=empty_audit) == []
    assert empty_audit.status == CollectionStatus.SUCCEEDED


def test_pagination_limits_malformed_records_and_partial_failure():
    limit_audit = audit()
    result = paginate(
        lambda _: ([{"id": "1"}, {}], "next"),
        identity=lambda row: row["id"],
        audit=limit_audit,
        max_pages=1,
    )
    assert result == [{"id": "1"}] and limit_audit.rejected == 1 and limit_audit.truncated
    partial_audit = audit()
    calls = 0

    def fetch(cursor):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TransportError(FailureCategory.PROVIDER_5XX, "token=secret")
        return [{"id": "1"}], "next"

    assert paginate(fetch, identity=lambda row: row["id"], audit=partial_audit) == [{"id": "1"}]
    assert (
        partial_audit.status == CollectionStatus.PARTIAL
        and partial_audit.failure_category == FailureCategory.PROVIDER_5XX
    )
    assert "secret" not in partial_audit.failure_reason


def test_registry_is_explicit_complete_and_secret_free(client):
    rows = public_capabilities(Settings())
    assert {row["provider"] for row in rows} == {
        "UCDP",
        "ACLED",
        "VIEWS",
        "CAST",
        "GDELT",
        "NEWSAPI",
    }
    assert all(row["integration_mode"] == "DISABLED" for row in rows)
    response = client.get("/providers")
    assert response.status_code == 200 and "access_token" not in response.text.casefold()


def test_gdelt_live_diagnostic_reports_only_sanitized_rate_limit_metadata(monkeypatch):
    module = import_module("geointel.providers.__main__")
    result_audit = CollectionAudit("GDELT", "0.1.3.1", IntegrationMode.OFFICIAL_API, "test")
    result_audit.failure_category = FailureCategory.RATE_LIMITED
    result_audit.rate_limited = True
    result_audit.retry_after_seconds = 45

    class RateLimitedConnector:
        connector_name = "GDELT"
        last_audit = result_audit

        def collect(self, location, horizon_months):
            del location, horizon_months
            error = RuntimeError("provider rate limited collection")
            error.category = FailureCategory.RATE_LIMITED
            raise error

    monkeypatch.setattr(
        module,
        "public_capabilities",
        lambda settings: [
            {
                "provider": "GDELT",
                "integration_mode": "OFFICIAL_API",
                "configured": True,
                "authentication_configured": True,
                "enabled": True,
            }
        ],
    )
    monkeypatch.setattr(module, "connectors", lambda settings: [RateLimitedConnector()])

    result = module._check_live("GDELT")

    assert result == {
        "provider": "GDELT",
        "mode": "OFFICIAL_API",
        "configured": True,
        "authentication_configured": True,
        "persisted": False,
        "alerts_created": False,
        "ok": False,
        "failure_category": "RATE_LIMITED",
        "message": "provider rate limited collection",
        "retry_after_seconds": 45,
    }
