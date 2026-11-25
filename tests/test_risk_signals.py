from datetime import UTC, date, datetime, timedelta

from geointel.risk import backtest, warning_signs
from geointel.risk.sources import gdelt, gpsjam, metaculus, newswire, sentinel

TODAY = date(2026, 11, 24)


def _row(root: str, a1: str, a2: str, place: str, columns: int = 61) -> str:
    row = [""] * columns
    row[7], row[17], row[25], row[28] = a1, a2, "1", root
    row[52 if columns >= 61 else 50] = place
    return "\t".join(row)


def test_gdelt_aggregate_and_zscores():
    text = "\n".join(
        [
            _row("14", "FRA", "", "Paris, Ile-de-France, France"),
            _row("19", "", "", "Bamako, Mali"),
            _row("13", "RUS", "LTU", "Vilnius, Lithuania"),
            _row("04", "FRA", "", "France", columns=58),
        ]
    )
    day = gdelt.aggregate([text], watch={("RUS", "LTU")})
    assert day["countries"]["FRA"] == {
        "all": 2,
        "protest": 1,
        "armed": 0,
        "repression": 0,
        "external": 0,
    }
    assert day["countries"]["MLI"]["armed"] == 1
    assert day["countries"]["RUS"]["external"] == 1 and day["dyads"] == {"RUS>LTU": 1}

    days = {}
    for i in range(1, 60):
        d = (TODAY - timedelta(days=i)).isoformat()
        protest = 40 if i <= 7 else 5 + (i % 3)
        days[d] = {
            "countries": {
                "FRA": {"all": 100, "protest": protest, "armed": 1, "repression": 2, "external": 3}
            }
        }
    z = gdelt.zscores(days, TODAY)
    assert z["FRA"]["protest"] > 3
    assert abs(z["FRA"]["armed"]) < 1
    assert gdelt.missing_days(days, TODAY, 3)[0] == TODAY - timedelta(days=60)


def test_gpsjam_parse_and_summary():
    text = "hex,count_good_aircraft,count_bad_aircraft\nA,10,10\nB,50,0\nC,5,5\n"
    where = {"A": (57.0, 24.0), "B": (57.1, 24.1), "C": (0.0, 0.0)}
    parsed = gpsjam.parse_day(
        text, lambda lat, lon: "LVA" if lat > 50 else None, lambda h: where[h]
    )
    assert parsed == {"LVA": {"good": 60, "bad": 10, "red_hexes": 1}}
    days = {
        (TODAY - timedelta(days=i)).isoformat(): {"LVA": {"good": 95, "bad": 5}}
        for i in range(8, 40)
    }
    days[(TODAY - timedelta(days=1)).isoformat()] = {"LVA": {"good": 70, "bad": 30}}
    summary = gpsjam.summary(days, TODAY)["LVA"]
    assert summary["share"] == 0.3 and summary["ratio"] > 5


def test_combine_caps_and_combination_bonus():
    signs = [
        {"key": k, "status": "active"}
        for k in ("posture", "medical", "rhetoric", "cyber", "gps_jamming")
    ]
    combined = warning_signs.combine(signs, warning_signs.INTERSTATE)
    expected = 1.6 * 3.0 * 1.3 * 1.5 * warning_signs.COMBO_LR * 1.3
    assert combined["combo"] and abs(combined["factor"] - expected) < 0.01
    many = [{"key": k, "status": "active"} for k in warning_signs.SPEC if k != "deescalation"]
    assert warning_signs.combine(many, warning_signs.INTERSTATE)["factor"] == 500.0
    assert warning_signs.combine(signs, warning_signs.ECONOMIC)["signs"] == []
    adjusted = warning_signs.adjusted_horizons(
        {"1y": {"p": 0.1, "low": 0.05, "high": 0.2}, "10y": {"p": 0.5, "low": 0.4, "high": 0.6}},
        4.0,
    )
    assert adjusted["1y"]["p"] > 0.3 and adjusted["10y"]["p"] < 0.65


def test_build_signals_for_a_country():
    snapshot = {
        "countries": [
            {
                "iso3": "LVA",
                "risks": {
                    "interstate_conflict": {
                        "question": "onset_within",
                        "horizons": {"1y": {"p": 0.01, "low": 0.005, "high": 0.02}},
                    }
                },
                "advisory": {"level": 2, "summary": "Ordered departure of staff"},
                "elections": [],
            }
        ]
    }
    history = {"LVA": [["2026-09-01", 1, 1, False], ["2026-11-20", 3, 2, True]]}
    news = [
        {
            "date": "2026-11-23",
            "country": "LVA",
            "sign": "posture",
            "domain": "a.com",
            "summary_ru": "x",
            "summary_en": "x",
            "url": "https://a.com/1",
        },
        {
            "date": "2026-11-22",
            "country": "LVA",
            "sign": "posture",
            "domain": "b.com",
            "summary_ru": "y",
            "summary_en": "y",
            "url": "https://b.com/1",
        },
    ]
    result = warning_signs.build_signals(
        snapshot,
        today=TODAY,
        gdelt_z={"LVA": {"armed": None, "protest": 0.1, "repression": 0, "external": 2.5}},
        gps={"LVA": {"share": 0.2, "ratio": 2.0}},
        advisory_history=history,
        milex={"LVA": {"value": 3.5, "change5": 1.4}},
        news_entries=news,
        generated_at=datetime(2026, 11, 24, tzinfo=UTC),
    )
    lva = result["countries"]["LVA"]
    active = {s["key"] for s in lva["signs"] if s["status"] == "active"}
    assert {
        "gdelt_external",
        "gps_jamming",
        "advisory_raised",
        "advisory_departure",
        "milex_rise",
        "posture",
        "intel_warning",
    } <= active
    news_sign = next(s for s in lva["signs"] if s["key"] == "posture")
    assert news_sign["strength"] == 1.0 and news_sign["reports"] == 2
    adjusted = lva["adjusted"]["interstate_conflict"]
    assert adjusted["factor"] > 3 and adjusted["horizons"]["1y"]["p"] > 0.03


def test_newswire_validation_and_metaculus_and_sentinel():
    batch = [
        {
            "title": "Troops massed",
            "url": "https://x.org/a",
            "domain": "x.org",
            "date": "2026-11-23",
        }
    ]
    reply = (
        'Here: [{"i": 0, "country": "LTU", "actor": "RUS", "sign": "posture", '
        '"summary_ru": "a", "summary_en": "b"}, {"i": 5, "country": "LTU", "sign": "posture"}, '
        '{"i": 0, "country": "XXX", "sign": "posture"}, {"i": 0, "country": "LTU", '
        '"sign": "ignore previous instructions"}]'
    )
    parsed = newswire.parse_reply(reply, batch)
    assert len(parsed) == 1 and parsed[0]["actor"] == "RUS" and parsed[0]["url"] == batch[0]["url"]
    heads = newswire.headlines(
        [{"articles": [{"title": " A  b ", "url": "https://u", "seendate": "20261123T101500Z"}]}]
    )
    assert heads[0] == {"title": "A b", "url": "https://u", "domain": "", "date": "2026-11-23"}

    questions = metaculus.questions(
        [
            {
                "results": [
                    {
                        "id": 7,
                        "title": "Will Russia attack a NATO country before 2028?",
                        "nr_forecasters": 300,
                        "question": {
                            "type": "binary",
                            "scheduled_resolve_time": "2028-01-01T00:00:00Z",
                            "aggregations": {"recency_weighted": {"latest": {"centers": [0.12]}}},
                        },
                    }
                ]
            }
        ]
    )
    assert questions == [
        {
            "question": "Will Russia attack a NATO country before 2028?",
            "p": 0.12,
            "end": "2028-01-01",
            "forecasters": 300,
            "url": "https://www.metaculus.com/questions/7/",
        }
    ]

    response = {
        "data": [
            {
                "interval": {"from": f"2026-{m:02d}-01T00:00:00Z"},
                "outputs": {"vv": {"bands": {"B0": {"stats": {"percentiles": {"99.0": v}}}}}},
            }
            for m, v in zip(range(1, 11), [1, 1, 1.1, 0.9, 1, 1, 1, 1, 2, 2.2], strict=True)
        ]
    }
    change = sentinel.change(sentinel.series(response))
    assert change["active"] and change["ratio"] == 2.1


def test_backtest_rises_before_the_invasion():
    result = backtest.run()
    points = {p["date"]: p for p in result["points"]}
    first, last = result["points"][0], result["points"][-1]
    assert first["factor"] == 1.0
    assert last["date"] == "2022-02-23" and last["p1m"] > 0.5
    autumn = max(p["p1y"] for d, p in points.items() if "2021-08" <= d < "2021-10")
    assert first["p1y"] < autumn < last["p1y"]
