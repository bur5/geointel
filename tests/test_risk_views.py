from datetime import date

from geointel.risk.sources import views


def test_latest_run_picks_newest_month_and_generation():
    runs = [
        "fatalities002_2025_06_t01",
        "fatalities003_2026_08_t01",
        "fatalities003_2026_09_t01",
        "fatalities001_2026_09_t01",
        "junk",
    ]
    assert views.latest_run(runs) == "fatalities003_2026_09_t01"


def test_compact_and_country_view():
    rows = [{"isoab": "MLI", "year": 2026, "month": m, "main_dich": 0.1} for m in range(10, 13)] + [
        {"isoab": "MLI", "year": 2027, "month": m, "main_dich": 0.2} for m in range(1, 13)
    ]
    data = views.compact(rows)
    view = views.country_view(data["MLI"], date(2026, 11, 27))
    assert view["p1m"] == 0.1
    assert view["p12m_low"] == 0.2
    assert view["p12m_low"] <= view["p12m"] <= view["p12m_high"] < 1
    # run does not cover the current month -> skipped, never guessed
    assert views.country_view(data["MLI"], date(2026, 9, 1)) is None


def test_apply_views_blends_only_onset_and_keeps_order():
    months = {f"2026-{m:02d}": 0.05 for m in range(11, 13)}
    months.update({f"2027-{m:02d}": 0.05 for m in range(1, 13)})

    def risk(question):
        return {
            "question": question,
            "horizons": {
                "1m": {"p": 0.001, "low": 0.0005, "high": 0.002},
                "1y": {"p": 0.01, "low": 0.005, "high": 0.02},
                "5y": {"p": 0.05, "low": 0.03, "high": 0.08},
                "10y": {"p": 0.1, "low": 0.06, "high": 0.15},
            },
        }

    snapshot = {
        "countries": [
            {"iso3": "AAA", "risks": {"internal_armed_conflict": risk("onset_within")}},
            {"iso3": "BBB", "risks": {"internal_armed_conflict": risk("active_at_end")}},
        ],
        "event_types": [{"key": "internal_armed_conflict"}],
    }
    payload = {"run": "fatalities003_2026_10_t01", "countries": {"AAA": months, "BBB": months}}
    n = views.apply_views(snapshot, payload, date(2026, 11, 2), "internal_armed_conflict")
    assert n == 1
    a = snapshot["countries"][0]["risks"]["internal_armed_conflict"]
    assert a["model"] == "views_blend"
    assert a["own_horizons"]["1y"]["p"] == 0.01
    ps = [a["horizons"][h]["p"] for h in ("1m", "1y", "5y", "10y")]
    assert ps == sorted(ps)
    assert a["horizons"]["1y"]["p"] > 0.01  # pulled toward ViEWS
    for h in a["horizons"].values():
        assert h["low"] <= h["p"] <= h["high"]
    b = snapshot["countries"][1]
    assert "model" not in b["risks"]["internal_armed_conflict"]
    assert b["external"]["views"]["run"] == "fatalities003_2026_10_t01"
    assert snapshot["event_types"][0]["views"]["countries"] == 1


def test_views_not_blended_for_a_country_at_interstate_war():
    months = {f"2026-{m:02d}": 0.99 for m in range(11, 13)}
    months.update({f"2027-{m:02d}": 0.99 for m in range(1, 13)})
    cell = {"p": 0.05, "low": 0.03, "high": 0.08}
    risk = {
        "question": "onset_within",
        "horizons": {h: dict(cell) for h in ("1m", "1y", "5y", "10y")},
    }
    snapshot = {
        "countries": [
            {
                "iso3": "UKR",
                "risks": {"internal_armed_conflict": risk, "interstate_conflict": {"active": True}},
            }
        ],
        "event_types": [],
    }
    payload = {"run": "r", "countries": {"UKR": months}}
    assert views.apply_views(snapshot, payload, date(2026, 11, 2), "internal_armed_conflict") == 0
    ukr = snapshot["countries"][0]
    assert ukr["risks"]["internal_armed_conflict"]["horizons"]["1y"]["p"] == 0.05
    assert ukr["external"]["views"]["skipped"] == "interstate_war"
