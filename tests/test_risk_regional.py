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
        {"iso3": "USA", "lat": 27.0, "lon": -82.0, "month": "2026-10", "deaths": 6},
        {"iso3": "USA", "lat": 36.0, "lon": -120.0, "month": "2026-01", "deaths": 30},
        {"iso3": "USA", "lat": 45.0, "lon": -93.0, "month": "2024-01", "deaths": 100},
    ]
    levels = ucdp_ged.region_levels(items, INDEX.locate, date(2026, 11, 27))["USA"]
    assert levels["FL"]["level"] == 5 and levels["CA"]["level"] == 4 and "MN" not in levels


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
