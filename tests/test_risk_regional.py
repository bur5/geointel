from geointel.risk.danger import apply_regional
from geointel.risk.regional import build_regional, weighted_median
from geointel.risk.regions import RegionIndex, simplified_geojson


def _square(code, name, x0, y0, x1, y1):
    return {
        "type": "Feature",
        "properties": {"iso_a2": "US", "name_en": name, "name_ru": name, "adm1_code": code},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
        },
    }


INDEX = RegionIndex(
    {
        "features": [
            _square("FL", "Florida", -87, 25, -80, 31),
            _square("MN", "Minnesota", -97, 43, -89, 49),
            _square("CA", "California", -124, 32, -114, 42),
        ]
    }
)


def test_weighted_median():
    assert weighted_median([(4, 0.1), (1, 0.9)]) == 1
    assert weighted_median([(4, 0.6), (1, 0.4)]) == 4


def test_florida_hurricane_does_not_paint_minnesota():
    events = [
        {"hazard": "TC", "year": y, "countries": ["USA"], "region_code": "FL"}
        for y in range(2001, 2025, 2)
    ]
    alerts = {"USA": [{"hazard": "TC", "name": "X", "alert": "Red", "lat": 27.0, "lon": -82.0}]}
    cities = {
        "USA": [(27.0, -82.0, 1_000_000), (45.0, -93.0, 3_000_000), (34.0, -118.0, 6_000_000)]
    }
    regional = build_regional(INDEX, events, alerts, cities, [], 2025)["USA"]
    assert regional["level_median"] == 1 and regional["level_max"] == 4
    assert regional["max_regions"][0]["code"] == "FL"
    assert regional["max_population_share"] == 0.1
    tc = regional["hazards"]["tropical_cyclone"]["regions"]
    assert tc[0]["code"] == "FL" and tc[0]["p_year"] > tc[-1]["p_year"]
    danger = apply_regional({"level": 1}, regional)
    assert danger["level"] == 1 and danger["regional"]["max"] == 4


def test_volcano_named_in_its_region():
    volcanoes = [
        {"name": "Mount Test", "country": "USA", "lat": 36.0, "lon": -120.0, "last_eruption": 1980}
    ]
    regional = build_regional(INDEX, [], {}, {}, volcanoes, 2025)["USA"]
    ca = next(r for r in regional["regions"] if r["code"] == "CA")
    assert ca["volcanoes"][0]["name"] == "Mount Test"


def test_simplified_geometry():
    geo = simplified_geojson(INDEX, "USA")
    assert {f["properties"]["code"] for f in geo["features"]} == {"FL", "MN", "CA"}


def test_regime_labels_parse():
    from geointel.risk.sources import outlook

    text = (
        "entity,code,year,regime_row_owid\n"
        "Norway,NOR,2024,Liberal democracy\nNorway,NOR,2025,Liberal democracy\n"
        "Mali,MLI,2025,Closed autocracy\n"
    )
    latest = outlook.owid_regime_latest(text)
    assert latest["NOR"] == {"value": 3, "year": 2025}
    assert latest["MLI"]["value"] == 0


def test_ged_links_and_region_levels():
    from datetime import date

    from geointel.risk.sources import ucdp_ged

    html = (
        '<a href="https://ucdp.uu.se/downloads/ged/ged251-csv.zip">'
        '<a href="https://ucdp.uu.se/downloads/ged/ged261-csv.zip">'
        '<a href="https://ucdp.uu.se/downloads/candidateged/GEDEvent_v26_01_26_09.csv">'
        '<a href="https://ucdp.uu.se/downloads/candidateged/GEDEvent_v26_0_9.csv">'
        '<a href="https://ucdp.uu.se/downloads/candidateged/GEDEvent_v26_0_10.csv">'
    )
    urls = ucdp_ged.links(html)
    assert urls["ged"].endswith("ged261-csv.zip")
    assert urls["candidate_latest"].endswith("v26_0_10.csv")
    assert urls["candidate_cumulative"].endswith("v26_01_26_09.csv")
    items = [
        {"iso3": "USA", "lat": 27.0, "lon": -82.0, "month": "2026-10", "deaths": 260, "type": 1},
        {"iso3": "USA", "lat": 36.0, "lon": -120.0, "month": "2026-01", "deaths": 160},
        {"iso3": "USA", "lat": 45.0, "lon": -93.0, "month": "2024-01", "deaths": 100},
    ]
    levels = ucdp_ged.region_levels(items, INDEX.locate, date(2026, 11, 27))["USA"]
    assert levels["FL"]["level"] == 5 and levels["CA"]["level"] == 4 and "MN" not in levels
    few = [{"iso3": "USA", "lat": 27.0, "lon": -82.0, "month": "2026-10", "deaths": 6}]
    cartel = [
        {"iso3": "USA", "lat": 27.0, "lon": -82.0, "month": "2026-10", "deaths": 400, "type": 2}
    ]
    assert (
        ucdp_ged.region_levels(cartel, INDEX.locate, date(2026, 11, 27))["USA"]["FL"]["level"] == 4
    )
    old = [{"iso3": "USA", "lat": 27.0, "lon": -82.0, "month": "2025-11", "deaths": 30}]
    assert "USA" not in ucdp_ged.region_levels(old, INDEX.locate, date(2026, 11, 27))
    assert ucdp_ged.region_levels(few, INDEX.locate, date(2026, 11, 27))["USA"]["FL"]["level"] == 2


def _xlsx(rows):
    import io
    import zipfile

    def cell(ref, v):
        return f'<c r="{ref}" t="inlineStr"><is><t>{v}</t></is></c>'

    body = "".join(
        f'<row r="{i + 1}">'
        + "".join(cell(f"{chr(65 + j)}{i + 1}", v) for j, v in enumerate(r))
        + "</row>"
        for i, r in enumerate(rows)
    )
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            f'<workbook {ns} {rel}><sheets><sheet name="Crises" '
            'sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.'
            'openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" '
            'Target="worksheets/sheet1.xml"/></Relationships>',
        )
        z.writestr(
            "xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{body}</sheetData></worksheet>"
        )
    return buf.getvalue()


def test_inform_severity_parse():
    from geointel.risk.sources import inform_severity

    payload = _xlsx(
        [
            ["INFORM Severity"],
            ["Crisis name", "ISO3", "INFORM Severity Index", "INFORM Severity category", "Impact"],
            ["Sudan conflict", "SDN", "4.9", "Very High", "5"],
            ["Sudan floods", "SDN", "3.1", "High", "3"],
            ["Haiti", "HTI", "4,2", "Very High", "4"],
        ]
    )
    parsed = inform_severity.parse(payload)
    assert parsed["SDN"]["score"] == 4.9 and parsed["SDN"]["crisis"] == "Sudan conflict"
    assert parsed["HTI"]["score"] == 4.2 and parsed["HTI"]["impact"] == 4.0


def test_ged_cells_dedupe_events_across_files():
    from geointel.risk.sources import ucdp_ged

    csv_text = (
        "id,year,date_start,latitude,longitude,best,country,type_of_violence\n"
        "7,2026,2026-10-03,48.0,37.8,10,Ukraine,1\n"
    )
    seen: set = set()
    first = ucdp_ged.cells(csv_text, 2025, seen)
    second = ucdp_ged.cells(csv_text, 2025, seen)
    assert len(first) == 1 and first[0]["type"] == 1 and second == []


def test_multi_country_event_is_placed_in_each_country():
    events = [
        {
            "hazard": "TC",
            "source": "gdacs",
            "year": y,
            "countries": ["USA", "MEX"],
            "lat": 28.0,
            "lon": -82.0,
        }
        for y in range(2001, 2025, 2)
    ]
    regional = build_regional(INDEX, events, {}, {}, [], 2025)["USA"]
    tc = regional["hazards"]["tropical_cyclone"]["regions"]
    assert tc[0]["code"] == "FL" and tc[0]["years"] == 12


def test_window_starts_at_the_source_used():
    gdacs = [
        {"hazard": "EQ", "source": "gdacs", "year": 2010, "countries": ["USA"], "region_code": "CA"}
    ]
    usgs = [
        {"hazard": "EQ", "source": "usgs", "year": y, "countries": ["USA"], "region_code": "CA"}
        for y in (1950, 2000)
    ]
    regional = build_regional(INDEX, gdacs + usgs, {}, {}, [], 2025)["USA"]
    eq = regional["hazards"]["major_earthquake"]
    assert eq["window"] == [1950, 2025]
    assert eq["regions"][0]["years"] == 2  # the GDACS duplicate is not mixed in
    only_gdacs = build_regional(INDEX, gdacs, {}, {}, [], 2025)["USA"]
    assert only_gdacs["hazards"]["major_earthquake"]["window"] == [2010, 2025]


def test_per_capita_thresholds_and_cartel_density():
    from geointel.risk.sources.ucdp_ged import conflict_level

    # 260 state-based deaths in 90 days: a war zone for 5 million people, not for 40 million.
    assert conflict_level(260, 260, 0, 0, 5_000_000) == 5
    assert conflict_level(260, 260, 0, 0, 40_000_000) == 4  # 0.65 per 100k in 90 days
    assert conflict_level(260, 260, 0, 0, None) == 5  # no population: absolute rule
    # Cartel violence: 4 only at 10+ per 100,000 a year.
    assert conflict_level(0, 0, 100, 400, 10_000_000) == 3
    assert conflict_level(0, 0, 100, 1_200, 10_000_000) == 4
    assert conflict_level(0, 0, 500, 5_000, 1_000_000) == 4  # never 5


def test_country_level_counts_only_people_near_fighting():
    from geointel.risk.popgrid import PopGrid, cell_of

    fl_hot = cell_of(27.0, -82.0)
    far = cell_of(30.5, -86.5)
    grid = PopGrid(
        {
            "version": 1,
            "regions": {"USA": {"FL": 6_000_000, "MN": 2_000_000, "CA": 3_000_000}},
            "cells": {
                "USA": {
                    "FL": [[*fl_hot, 500_000], [*far, 5_500_000]],
                    "MN": [[*cell_of(45.0, -93.0), 2_000_000]],
                    "CA": [[*cell_of(34.0, -118.0), 3_000_000]],
                }
            },
        }
    )
    extra = {"USA": {"FL": {"level": 5, "reason_ru": "", "reason_en": "", "hot_cells": [fl_hot]}}}
    regional = build_regional(INDEX, [], {}, {}, [], 2025, extra, grid)["USA"]
    fl = next(r for r in regional["regions"] if r["code"] == "FL")
    assert fl["level"] == 5 and fl["zone_population"] == 500_000
    assert regional["population_source"] == "ghsl"
    # Without the zone split Florida (6 of 11 million) would set the country to 5.
    assert regional["level_median"] == 1 and regional["level_max"] == 5
    assert regional["max_population_share"] == round(500_000 / 11_000_000, 3)
    assert "hot_cells" not in fl["reasons"][0]
