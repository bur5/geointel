import json

import pytest

httpx = pytest.importorskip("httpx")

from geointel.risk import fetch  # noqa: E402


def test_elections_keep_cached_countries_when_batches_fail(tmp_path, monkeypatch):
    cached = {"results": {"bindings": [{"iso3": {"value": "FRA"}, "e": {"value": "old"}}]}}
    (tmp_path / "elections.json").write_text(json.dumps(cached))
    monkeypatch.setenv("GEOINTEL_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(fetch.time, "sleep", lambda _s: None)

    def handler(request):
        query = request.url.params.get("query", "")
        if "VALUES" not in query:  # country list
            rows = [
                {
                    "country": {"value": "http://www.wikidata.org/entity/Q142"},
                    "iso3": {"value": "FRA"},
                },
                {
                    "country": {"value": "http://www.wikidata.org/entity/Q183"},
                    "iso3": {"value": "DEU"},
                },
            ]
            return httpx.Response(200, json={"results": {"bindings": rows}})
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        payload, _url, version = fetch._elections(client, 2026)
    bindings = json.loads(payload)["results"]["bindings"]
    assert [b["e"]["value"] for b in bindings] == ["old"]
    assert "0 of 2" in version
