import json
from pathlib import Path

from geointel.risk.hazards import build_hazard_details
from geointel.risk.model import TypeHistory, assess_type
from geointel.risk.sources import fts, gdacs, ncei_tsunami, usgs, worldbank
from geointel.risk.taxonomy import EventType

FIXTURES = Path(__file__).parent / "fixtures" / "risk"


def test_gdacs_keeps_orange_red_and_dedupes():
    events = gdacs.normalize_all(
        json.loads((FIXTURES / "gdacs_sample.json").read_text())["features"]
    )
    ids = {e["id"]: e for e in events}
    assert set(ids) == {"TC-1000001", "FL-2000002", "VO-4"}
    assert ids["TC-1000001"]["alert"] == "Red"
    assert ids["TC-1000001"]["countries"] == ["PHL", "VNM"]
    assert ids["VO-4"]["countries"] == ["IDN"]  # falls back to the country name
    histories = gdacs.histories(events, reference_year=2026)
    assert histories[EventType.TROPICAL_CYCLONE].years_with_event["VNM"] == {2013}
    assert histories[EventType.FLOOD].years_with_event["BGD"] == {2020}
    assert "IDN" not in histories[EventType.VOLCANO].years_with_event  # 2026 is incomplete


def test_tsunami_parser_filters_validity():
    events = ncei_tsunami.normalize_all(json.loads((FIXTURES / "tsunami_sample.json").read_text()))
    by_id = {e["id"]: e for e in events}
    assert set(by_id) == {"TS-1", "TS-2", "TS-4"}
    assert by_id["TS-1"]["countries"] == ["JPN"] and by_id["TS-1"]["alert"] == "Red"
    history = ncei_tsunami.history(events, reference_year=2026)
    assert history.years_with_event["IDN"] == {2018}
    assert history.unresolved_labels == 1


def _wb(rows):
    return [{"page": 1}, [{"countryiso3code": c, "date": str(y), "value": v} for c, y, v in rows]]


def test_worldbank_crisis_years_and_gaps():
    gdp = _wb(
        [
            ("ARG", 2001, -4.4),
            ("ARG", 2002, -10.9),
            ("ARG", 2003, 8.8),
            ("DEU", 2009, -5.7),
            ("DEU", 2010, 4.2),
            ("WLD", 2009, -1.3),
        ]
        + [(f"X{i}", 2010, 1.0) for i in range(3)]
    )
    inflation = _wb([("ZWE", 2008, 1000.0), ("ZWE", 2010, 3.0), ("ARG", 2003, 13.0)])
    history = worldbank.history(gdp, inflation)
    assert history.years_with_event["ARG"] == {2001, 2002}
    assert history.years_with_event["ZWE"] == {2008}
    assert "WLD" not in (history.observed_years or {})


def test_observed_years_skip_countries_without_data():
    history = TypeHistory(
        event_type=EventType.ECONOMIC_CRISIS,
        source="t",
        start_year=2000,
        end_year=2005,
        years_with_event={"AAA": frozenset({2001})},
        observed_years={"AAA": frozenset(range(2000, 2006)), "BBB": frozenset({2000, 2001, 2004})},
    )
    results = {
        r.iso3: r for r in assess_type(history, {"AAA": None, "BBB": None, "CCC": None}, False)
    }
    assert set(results) == {"AAA", "BBB"}
    assert results["BBB"].exposure_years == 3


def test_fts_counts_single_country_plans_only():
    payload = {
        2023: {
            "data": [
                {"locations": [{"iso3": "SDN", "adminLevel": 0}]},
                {"locations": [{"iso3": "UKR", "adminLevel": 0}, {"iso3": "POL", "adminLevel": 0}]},
            ]
        },
        2024: {
            "data": [
                {"locations": [{"iso3": "SDN", "adminLevel": 0}, {"iso3": "SDN", "adminLevel": 1}]}
            ]
        },
    }
    history = fts.history(payload)
    assert history.years_with_event == {"SDN": frozenset({2023, 2024})}
    assert history.end_year == 2024


def test_hazard_details_group_by_country_and_month():
    quakes = usgs.events((FIXTURES / "usgs_sample.csv").read_text())
    tsunamis = ncei_tsunami.normalize_all(
        json.loads((FIXTURES / "tsunami_sample.json").read_text())
    )
    details = build_hazard_details(quakes + tsunamis)
    japan = details["countries"]["JPN"]
    assert japan["major_earthquake"]["count"] == 2
    assert japan["major_earthquake"]["months"][2] == 1  # March 2011
    assert japan["tsunami"]["events"][0]["severity"].startswith("39 m")
    assert japan["major_earthquake"]["events"][0]["lat"] == 38.3
