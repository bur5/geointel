from datetime import date
from pathlib import Path

from geointel.risk.sources import jwc

PAGE = (Path(__file__).parent / "fixtures" / "jwc_listed.html").read_text(encoding="utf-8")


def test_parse_listed_areas():
    listed = jwc.parse(PAGE)
    assert listed["circular"] == "JWLA-035" and listed["issued"] == "2026-09-16"
    areas = listed["areas"]
    assert areas["RUS"]["partial"] is False  # the country is listed, not only the Sea of Azov
    assert areas["UKR"]["partial"] is True
    assert areas["GUY"]["partial"] is True
    assert {"IRN", "IRQ", "ISR", "YEM", "SDN", "VEN"} <= set(areas)


def test_first_seen_is_unknown_on_first_run_then_dated():
    today = date(2026, 11, 27)
    first = jwc.with_first_seen({"areas": {"IRN": {}}}, None, today)
    assert first["first_seen"] == {"IRN": None}
    later = jwc.with_first_seen({"areas": {"IRN": {}, "QAT": {}}}, first, date(2026, 12, 1))
    assert later["first_seen"] == {"IRN": None, "QAT": "2026-12-01"}
