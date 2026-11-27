from datetime import date, timedelta

from geointel.risk import early_signals, warning_signs
from geointel.risk.sources import coups, early, sentinel, telegram

TODAY = date(2026, 11, 25)


def test_cline_coups_and_links():
    text = (
        "coup_id,cowcode,country,year,month,day,event_type,unrealized,realized,conspiracy\n"
        "1,436,Niger,2023,7,26,coup,0,1,0\n"
        "2,436,Niger,2021,3,31,attempted,1,0,0\n"
        "3,432,Mali,2022,5,16,conspiracy,1,0,1\n"
    )
    history = coups.parse_any(text, 2026)
    assert history.years_with_event["NER"] == frozenset({2021, 2023})
    assert "MLI" not in history.years_with_event
    page = (
        '<a href="/datafiles/abc12/download">Coup Data 2.2.2.csv</a>'
        '<a href="/datafiles/zz/download">Codebook.pdf</a>'
    )
    assert coups.cline_csv_links(page) == [
        "https://databank.illinois.edu/datafiles/abc12/download",
        "https://aws-databank-alb.library.illinois.edu/datafiles/abc12/download",
    ]


def test_early_parsers():
    windows = early.weekly_windows(TODAY, 2)
    assert windows[0][1].weekday() == 6 and windows[0][0] == windows[0][1] - timedelta(days=6)
    timeline = early.doc_timeline(
        {"timeline": [{"data": [{"date": "20261120T000000Z", "value": 4}]}]}
    )
    assert timeline == {"2026-11-20": 4.0}
    counts = early.military_counts(
        [
            {
                "ac": [
                    {"hex": "a", "lat": 57.0, "lon": 24.0},
                    {"hex": "b", "lat": 25.0, "lon": 120.0},
                ]
            },
            {"ac": [{"hex": "a", "lat": 57.1, "lon": 24.1}]},
        ]
    )
    assert counts["baltic"] == 1 and counts["taiwan"] == 1
    ioda = early.ioda_countries(
        {"data": [{"entity": {"code": "IR"}, "scores": {"overall": 120}, "event_cnt": 4}]}
    )
    assert ioda == {"IRN": {"score": 120.0, "events": 4}}
    history = {
        (TODAY - timedelta(days=40)).isoformat(): {"TRY": 30.0},
        TODAY.isoformat(): {"TRY": 36.0},
    }
    assert early.fx_change(history, "TRY", TODAY)["change30"] == 0.2
    food = early.food_prices(
        "countryiso3,date,price_basket_change_1m\n#country,#date,#value\nYEM,2026-10-15,12.5\n"
    )
    assert food["YEM"]["change_1m"] == 12.5


def test_telegram_page_and_keyword_tally():
    page = (
        '<div class="tgme_widget_message_wrap x" data-post="rybar/120">'
        '<div class="tgme_widget_message_text js-x" dir="auto">'
        "Эшелон с техникой у границы с Латвией</div>"
        '<time datetime="2026-11-24T10:00:00+00:00"></time></div>'
        '<div class="tgme_widget_message_wrap y" data-post="rybar/119">'
        '<div class="tgme_widget_message_text" dir="auto">'
        'Погода</div><time datetime="2026-11-24T11:00:00+00:00"></time></div>'
    )
    posts = telegram.parse_page(page)
    assert [p["date"] for p in posts] == ["2026-11-24", "2026-11-24"]
    assert telegram.oldest_id(posts) == 119
    tally = telegram.count(posts + posts, "rybar")  # a post seen twice counts once
    assert tally["LVA"]["2026-11-24"] == {"n": 1, "military": 1}
    assert tally["UKR"]["2026-11-24"] == {"n": 1}  # no country named: channel default
    merged = telegram.merge(
        {"rybar": {"2026-11-01": {"posts": 3, "hits": 1}}}, {"rybar": tally}, date(2026, 11, 1)
    )
    assert merged["rybar"]["LVA"]["2026-11-24"]["military"] == 1  # old format dropped


def test_keyword_categories_and_countries():
    from geointel.risk.sources import keywords

    assert keywords.countries("Nigeria protests") == set()
    assert keywords.countries("Niger junta mutiny") == {"NER"}
    assert keywords.countries("малина и грузить") == set()
    assert keywords.countries("В Мали переворот") == {"MLI"}
    assert keywords.categories("Mass protests and a general strike") == {"unrest"}
    assert "emergency" in keywords.categories("Президент ввёл военное положение")
    days = {"2026-11-01": {"n": 10, "unrest": 2}, "2026-11-02": {"n": 2, "unrest": 2}}
    assert keywords.share_series(days, "unrest") == {"2026-11-01": 0.2}


def test_sentinel_seasonal_baseline():
    start = date(2025, 10, 1)
    points = [((start + timedelta(days=6 * i)).isoformat(), 1.0) for i in range(70)]
    # a year ago the same season was as bright as now: snow, not a build-up
    points = [(d, 2.0 if "2025-11-15" <= d <= "2025-12-15" else v) for d, v in points]
    points[-1] = (points[-1][0], 2.0)
    points[-2] = (points[-2][0], 2.0)
    result = sentinel.change(points)
    assert result["ratio"] == 2.0 and result["seasonal_ratio"] is not None
    assert result["active"] is (result["seasonal_ratio"] >= 1.4)


def test_early_signals_build_and_persistence(tmp_path):
    cache_in, cache_out = tmp_path / "in", tmp_path / "out"
    cache_in.mkdir()
    cache_out.mkdir()
    fx_days = {(TODAY - timedelta(days=i)).isoformat(): {"TRY": 30.0} for i in range(31, 60)}
    (cache_in / "fx.json").write_text(__import__("json").dumps({"days": fx_days}))
    mil = {(TODAY - timedelta(days=i)).isoformat(): {"baltic": 4} for i in range(1, 20)}
    (cache_in / "military.json").write_text(__import__("json").dumps({"days": mil}))
    signs, notes = early_signals.build(
        raw={
            "fx": {TODAY.isoformat(): {"TRY": 36.0}},
            "military": {"baltic": 20},
            "ioda": {"IRN": {"score": 50.0, "events": 5}},
        },
        cache_in=cache_in,
        cache_out=cache_out,
        today=TODAY,
        locate=None,
        conflict_countries=set(),
    )
    active = {(c, s["key"]) for c, items in signs.items() for s in items if s["status"] == "active"}
    assert ("TUR", "currency_crash") in active
    assert ("LTU", "military_air") in active
    assert ("IRN", "internet_outage") in active
    assert (cache_out / "fx.json").exists() and notes["fx"]

    country = {"iso3": "IRN", "risks": {}}
    entry = warning_signs.country_entry(country, signs["IRN"])
    history = {
        "countries": {
            "IRN": [
                [(TODAY - timedelta(days=i)).isoformat(), 1.4, ["internet_outage"]]
                for i in range(1, 13)
            ]
        }
    }
    (cache_in / "signals_history.json").write_text(__import__("json").dumps(history))
    trends = early_signals.persistence(
        cache_in / "signals_history.json", cache_out / "signals_history.json", {"IRN": entry}, TODAY
    )
    assert trends["IRN"]["persistent"] == ["internet_outage"]
    assert trends["IRN"]["recent5"]["internet_outage"] == 5
    factor = lambda e: e["adjusted"]["internal_armed_conflict"]["factor"]  # noqa: E731
    boosted = warning_signs.apply_persistence(country, entry, {"internet_outage"})
    fresh = warning_signs.apply_persistence(country, entry, set(), {"internet_outage": 1})
    confirmed = warning_signs.apply_persistence(country, entry, set(), {"internet_outage": 3})
    assert factor(boosted) > factor(confirmed) == factor(entry) > factor(fresh)
    # slow official data (exchange rates) is not discounted as a one-day spike
    tur = warning_signs.country_entry({"iso3": "TUR", "risks": {}}, signs["TUR"])
    assert warning_signs.apply_persistence({"iso3": "TUR", "risks": {}}, tur, set(), {}) is tur


def test_backtest_real_evaluate_on_synthetic_days():
    from geointel.risk import backtest_real

    case = backtest_real.Case(
        "x", "x", "x", "2022-02-24", "2021-12-01", "UKR", "RUS", "interstate_conflict", 0.05
    )
    days = {}
    for d in backtest_real.days_needed(case):
        hot = d >= date(2022, 1, 20)
        days[d.isoformat()] = {
            "countries": {
                "UKR": {
                    "all": 100,
                    "external": 30 if hot else 5 + d.day % 3,
                    "protest": 2,
                    "armed": 1,
                    "repression": 1,
                }
            },
            "dyads": {"RUS>UKR": 20 if hot else 2},
        }
    result = backtest_real.evaluate(case, days)
    early_points = [p for p in result["points"] if p["date"] < "2022-01-15"]
    late_points = [p for p in result["points"] if p["date"] >= "2022-02-01"]
    assert all(p["factor"] == 1.0 for p in early_points)
    assert all("gdelt_external" in p["signs"] for p in late_points)
    assert result["lead_days"] > 0 and result["brier"] is not None
