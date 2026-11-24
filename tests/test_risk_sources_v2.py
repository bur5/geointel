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


def test_travel_advisories_parse_level_and_country():
    from geointel.risk.sources import advisories

    items = [
        {
            "Title": "Belarus - Level 4: Do Not Travel",
            "Link": "u1",
            "Category": ["BO"],
            "Summary": "<p><b>Do not travel</b> due to&nbsp;risk</p>",
            "Updated": "2025-09-04",
        },
        {"Title": "Mexico - Level 2: Exercise Increased Caution", "Link": "u2", "Summary": ""},
        {"Title": "Atlantis - Level 1: Exercise Normal Precautions"},
        {"Title": "Something without a level"},
    ]
    parsed, unresolved = advisories.parse(items)
    assert parsed["BLR"]["level"] == 4 and parsed["BLR"]["summary"] == "Do not travel due to risk"
    assert parsed["MEX"]["level"] == 2
    assert unresolved == 1


def test_exposure_latest_values_and_world_share():
    from geointel.risk.sources import exposure

    def payload(rows):
        return [{}, [{"countryiso3code": c, "date": str(y), "value": v} for c, y, v in rows]]

    data = {
        "NY.GDP.MKTP.CD": payload(
            [("USA", 2023, 75.0), ("USA", 2024, 80.0), ("SAU", 2024, 20.0), ("WLD", 2024, 100.0)]
        ),
        "NY.GDP.PETR.RT.ZS": payload([("SAU", 2022, 25.0), ("SAU", 2023, None)]),
    }
    profiles = exposure.latest(data)
    assert profiles["USA"]["gdp_usd"] == {"value": 80.0, "year": 2024}
    assert profiles["SAU"]["oil_rents_gdp"]["year"] == 2022
    assert profiles["USA"]["world_gdp_share"]["value"] == 80.0


def test_imf_outlook_flags_projected_crisis():
    from geointel.risk.sources import outlook

    payloads = {
        "NGDP_RPCH": {
            "values": {
                "NGDP_RPCH": {
                    "ARG": {"2025": 4.5, "2026": -3.5, "2027": 2.0},
                    "WEOWORLD": {"2026": 3},
                }
            }
        },
        "PCPIPCH": {"values": {"PCPIPCH": {"VEN": {"2026": 180.0, "2027": 150.0}}}},
    }
    result = outlook.imf_outlook(payloads, reference_year=2026)
    assert result["ARG"]["projects_crisis"] == ["2026"]
    assert result["VEN"]["projects_crisis"] == ["2026", "2027"]
    assert "WEOWORLD" not in result


def test_owid_latest_and_gpr_series():
    from geointel.risk.sources import outlook

    text = (
        "Entity,Code,Year,electdem_vdem\nRussia,RUS,2023,0.11\nRussia,RUS,2024,0.1\n"
        "Kosovo,OWID_KOS,2024,0.6\nWorld,OWID_WRL,2024,0.4\n"
    )
    latest = outlook.owid_latest(text)
    assert latest["RUS"] == {"value": 0.1, "year": 2024} and latest["XKX"]["value"] == 0.6
    months = [f"20{y:02d}-{m:02d}" for y in range(20, 27) for m in range(1, 13)]
    columns = {"GPRC_ISR": [1.0] * (len(months) - 12) + [3.0] * 12, "GPR": [1] * len(months)}
    series = outlook.gpr_country_series(columns, months)
    assert set(series) == {"ISR"}
    assert series["ISR"]["ratio_12m"] == 3.0 and len(series["ISR"]["values"]) == 24


def test_elections_filter_national_only():
    from datetime import date

    from geointel.risk.sources import elections

    def b(entity, iso3, name, kind_label, when, precision=11):
        return {
            "e": {"value": f"http://www.wikidata.org/entity/{entity}"},
            "iso3": {"value": iso3},
            "eLabelEn": {"value": name},
            "typeLabel": {"value": kind_label},
            "date": {"value": when},
            "precision": {"value": str(precision)},
        }

    payload = {
        "results": {
            "bindings": [
                b(
                    "Q1",
                    "FRA",
                    "2027 French presidential election",
                    "presidential election",
                    "2027-04-10T00:00:00Z",
                ),
                b(
                    "Q2",
                    "FRA",
                    "2026 Paris municipal election",
                    "municipal election",
                    "2026-03-15T00:00:00Z",
                ),
                b(
                    "Q3",
                    "BRA",
                    "2026 Brazilian general election",
                    "general election",
                    "2026-10-04T00:00:00Z",
                ),
                b(
                    "Q4",
                    "USA",
                    "2026 Ohio gubernatorial election",
                    "gubernatorial election",
                    "2026-11-03T00:00:00Z",
                ),
                b(
                    "Q5",
                    "ITA",
                    "Italian constitutional referendum",
                    "referendum",
                    "2027-01-01T00:00:00Z",
                    9,
                ),
            ]
        }
    }
    parsed = elections.parse(payload, today=date(2026, 11, 24))
    assert set(parsed) == {"FRA", "BRA", "ITA"}
    assert parsed["FRA"][0]["kind"] == "presidential"
    assert parsed["ITA"][0]["precision"] == "year" and parsed["ITA"][0]["kind"] == "referendum"


def test_fcdo_levels_and_restrictions():
    from geointel.risk.sources import fcdo

    page = {
        "title": "Ethiopia travel advice",
        "web_url": "https://www.gov.uk/foreign-travel-advice/ethiopia",
        "details": {
            "alert_status": [
                "avoid_all_travel_to_parts",
                "avoid_all_but_essential_travel_to_parts",
            ],
            "parts": [
                {
                    "slug": "warnings-and-insurance",
                    "body": (
                        "<p>FCDO advises against all travel to:</p>"
                        "<ul><li>Amhara region</li></ul><p>Long text</p>"
                    ),
                }
            ],
        },
    }
    code, entry = fcdo.parse_country(page)
    assert code == "ETH" and entry["level"] == 2 and entry["partial"]
    assert entry["restrictions"][:2] == ["FCDO advises against all travel to:", "• Amhara region"]
    code, entry = fcdo.parse_country(
        {"title": "USA travel advice", "details": {"alert_status": []}}
    )
    assert code == "USA" and entry["level"] == 1


def test_region_index_point_in_polygon_and_nearest():
    from geointel.risk.regions import RegionIndex, annotate

    square = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
    other = {"type": "Polygon", "coordinates": [[[10, 0], [20, 0], [20, 10], [10, 10], [10, 0]]]}
    index = RegionIndex(
        {
            "features": [
                {
                    "properties": {"iso_a2": "JP", "name_en": "West", "name_ru": "Запад"},
                    "geometry": square,
                },
                {
                    "properties": {"iso_a2": "JP", "name_en": "East", "name_ru": "Восток"},
                    "geometry": other,
                },
            ]
        }
    )
    assert index.locate("JPN", 5, 15) == ("East", "Восток")
    assert index.locate("JPN", 5, -1) == ("West", "Запад")  # offshore, nearest region
    assert index.locate("JPN", 50, 50) is None
    events = [
        {"countries": ["JPN"], "lat": 5, "lon": 5},
        {"countries": ["JPN", "KOR"], "lat": 5, "lon": 5},
    ]
    annotate(events, index)
    assert events[0]["region_ru"] == "Запад" and "region_en" not in events[1]
