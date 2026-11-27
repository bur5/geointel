from datetime import date

from geointel.risk.sources import radar

PAYLOAD = {
    "result": {
        "annotations": [
            {
                "locations": ["IR"],
                "startDate": "2026-11-24T08:00:00Z",
                "endDate": None,
                "outage": {"outageCause": "GOVERNMENT_DIRECTED", "outageType": "NATIONWIDE"},
                "description": "Shutdown",
                "linkedUrl": "https://example.org",
            },
            {
                "locationsDetails": [{"code": "CU", "name": "Cuba"}],
                "startDate": "2026-11-20T00:00:00Z",
                "endDate": "2026-11-21T00:00:00Z",
                "outage": {"outageCause": "POWER_OUTAGE"},
            },
            {"locations": ["FR"], "startDate": "2026-10-01T00:00:00Z", "endDate": "2026-10-02"},
        ]
    }
}


def test_outages_parse_and_select_recent():
    records = radar.outages(PAYLOAD)
    assert records[0]["countries"] == ["IR"] and records[1]["countries"] == ["CU"]
    now = radar.by_country(records, {"IR": "IRN", "CU": "CUB", "FR": "FRA"}, date(2026, 11, 27))
    assert set(now) == {"IRN", "CUB"}
    assert radar.political(now["IRN"][0]["cause"])
    assert not radar.political(now["CUB"][0]["cause"])
