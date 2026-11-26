import json

import httpx

from geointel.risk import fetch


def test_newswire_sends_real_key_and_survives_rate_limits(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-value")
    monkeypatch.setattr(fetch.time, "sleep", lambda _s: None)
    seen_keys = []
    calls = {"doc": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.anthropic.com":
            seen_keys.append(request.headers.get("x-api-key"))
            body = {"content": [{"type": "text", "text": "[]"}], "usage": {"input_tokens": 5}}
            return httpx.Response(200, json=body)
        calls["doc"] += 1
        if calls["doc"] % 3 == 1:
            return httpx.Response(429, text="Please limit requests")
        if calls["doc"] % 3 == 2:
            return httpx.Response(200, text="not json")
        article = {
            "title": f"Headline {calls['doc']}",
            "url": f"https://example.org/{calls['doc']}",
            "seendate": "20261125T120000Z",
        }
        return httpx.Response(200, json={"articles": [article]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        payload, _url, version = fetch._newswire(client, 2026)

    assert seen_keys and set(seen_keys) == {"sk-test-value"}
    assert json.loads(payload)["headlines"] > 0
    assert "headlines" in version


def test_newswire_stops_fetching_after_time_budget(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-value")
    monkeypatch.setattr(fetch.time, "sleep", lambda _s: None)
    clock = iter(range(0, 10_000, 200))
    monkeypatch.setattr(fetch.time, "monotonic", lambda: next(clock))
    doc_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.anthropic.com":
            return httpx.Response(200, json={"content": [], "usage": {}})
        doc_calls.append(request.url)
        return httpx.Response(200, json={"articles": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        fetch._newswire(client, 2026)

    assert 0 < len(doc_calls) < 5
