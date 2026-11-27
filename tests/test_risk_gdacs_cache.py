import json

import pytest

httpx = pytest.importorskip("httpx")

from geointel.risk import fetch  # noqa: E402
from geointel.risk.sources import gdacs  # noqa: E402


def test_gdacs_reuses_cached_past_years(tmp_path, monkeypatch):
    old = {"properties": {"eventid": 1, "fromdate": "2015-03-01T00:00:00"}}
    recent = {"properties": {"eventid": 2, "fromdate": "2026-01-01T00:00:00"}}
    (tmp_path / "gdacs.json").write_text(json.dumps({"features": [old, recent]}))
    monkeypatch.setenv("GEOINTEL_CACHE_DIR", str(tmp_path))
    years = []

    def handler(request):
        years.append(request.url.params.get("fromdate", "")[:4])
        return httpx.Response(
            200, json={"features": [{"properties": {"eventid": 3, "fromdate": "2026-05-01"}}]}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        payload, _url, version = fetch._gdacs(client, 2026)
    assert set(years) == {"2025", "2026"}
    ids = {f["properties"]["eventid"] for f in json.loads(payload)["features"]}
    assert 1 in ids and 3 in ids and 2 not in ids  # recent years are refetched, not cached
    assert "from cache" in version
    assert len(years) == 2 * len(gdacs.HAZARDS)
