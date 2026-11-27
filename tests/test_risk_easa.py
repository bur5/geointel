from datetime import date
from pathlib import Path

from geointel.risk.sources import easa

PAGE = (Path(__file__).parent / "fixtures" / "easa_czib.html").read_text(encoding="utf-8")


def test_parse_rows_and_countries():
    items = easa.parse(PAGE)
    by_title = {i["title"]: i for i in items}
    saudi = by_title["Airspace of Saudi Arabia"]
    assert saudi["iso3"] == "SAU" and saudi["active"] and not saudi["partial"]
    assert saudi["issued"] == "2026-09-30" and saudi["valid_until"] == "2027-01-31"
    assert by_title["Airspace of Jordan"]["iso3"] == "JOR"
    assert by_title["Airspace of the Russian Federation"]["iso3"] == "RUS"
    pak = next(i for i in items if i["title"].startswith("Airspace of Pakistan"))
    assert pak["iso3"] == "PAK" and pak["partial"]
    gulf = by_title["Airspace of the Persian Gulf and Gulf of Oman"]
    assert gulf["iso3"] is None
    assert any(not i["active"] for i in items)


def test_current_marks_fresh_and_drops_withdrawn():
    items = easa.parse(PAGE)
    now = easa.current(items, date(2026, 11, 27))
    assert now["SAU"]["fresh"] is True
    assert now["RUS"]["fresh"] is False
    assert all(v["active"] for v in now.values())
    later = easa.current(items, date(2027, 6, 1))
    assert "SAU" not in later  # past its validity date
