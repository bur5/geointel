from geointel.risk.sources import advisories_extra as ax


def test_canada_levels_and_partial():
    payload = {
        "data": {
            "AF": {
                "country-iso": "AF",
                "advisory-state": 3,
                "has-regional-advisory": 0,
                "eng": {"url-slug": "afghanistan", "advisory-text": "Avoid all travel"},
                "date-published": {"date": "2026-11-25 14:19:24"},
            },
            "FR": {"country-iso": "FR", "advisory-state": 1, "has-regional-advisory": 1, "eng": {}},
            "ZZ": {"country-iso": "ZZ", "advisory-state": 0},
        }
    }
    parsed = ax.parse_canada(payload)
    assert parsed["AFG"]["level"] == 4 and parsed["AFG"]["url"].endswith("afghanistan")
    assert parsed["FRA"] == {**parsed["FRA"], "level": 2, "partial": True}
    assert "ZZ" not in parsed and len(parsed) == 2


def test_germany_flags():
    payload = {
        "response": {
            "lastModified": 1,
            "1": {"iso3CountryCode": "UKR", "warning": True, "title": "Ukraine"},
            "2": {"iso3CountryCode": "TUR", "partialWarning": True},
            "3": {"iso3CountryCode": "SWE", "warning": False},
            "4": {"iso3CountryCode": "XXX", "warning": True},
        }
    }
    parsed = ax.parse_germany(payload)
    assert parsed["UKR"]["level"] == 4
    assert parsed["TUR"]["level"] == 3 and parsed["TUR"]["partial"]
    assert parsed["SWE"]["level"] == 1 and "XXX" not in parsed
