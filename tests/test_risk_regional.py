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
