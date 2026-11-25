from datetime import UTC, datetime

from geointel.risk import scenarios
from geointel.risk.links import build_links
from geointel.risk.sources import migration, polymarket, trade, ucdp_acd

NOW = datetime(2026, 11, 24, tzinfo=UTC)


def _search_payload():
    return {
        "events": [
            {
                "title": "China x Taiwan",
                "slug": "china-invade-taiwan-2027",
                "endDate": "2027-12-31T00:00:00Z",
                "markets": [
                    {
                        "id": "1",
                        "question": "Will China invade Taiwan by December 31, 2027?",
                        "outcomes": '["Yes", "No"]',
                        "outcomePrices": '["0.08", "0.92"]',
                        "endDate": "2027-12-31T00:00:00Z",
                        "volume": "250000",
                        "oneMonthPriceChange": 0.01,
                    },
                    {
                        "id": "2",
                        "question": "Closed market",
                        "outcomes": ["Yes", "No"],
                        "outcomePrices": ["0.5", "0.5"],
                        "closed": True,
                        "endDate": "2027-01-01T00:00:00Z",
                        "volume": 1,
                    },
                ],
            },
            {
                "title": "Scalar",
                "markets": [
                    {
                        "id": "3",
                        "question": "How many?",
                        "outcomes": '["Up", "Down"]',
                        "outcomePrices": '["0.4", "0.6"]',
                        "endDate": "2027-01-01T00:00:00Z",
                    }
                ],
            },
        ]
    }


def test_polymarket_parses_open_binary_markets_only():
    found = polymarket.markets([_search_payload(), _search_payload()])
    assert len(found) == 1
    market = found[0]
    assert market["p"] == 0.08 and market["end"] == "2027-12-31" and market["volume"] == 250000
    assert polymarket.matches(market["question"], [("china",), ("taiwan",), ("invade",)])
    assert not polymarket.matches(market["question"], [("china",)], exclude=("invade",))


def test_scenarios_pool_components_and_list_affected_countries():
    dyads = ucdp_acd.dyad_years(
        "conflict_id,location,side_a,side_b,year,type_of_conflict\n"
        "1,India; Pakistan,Government of India,Government of Pakistan,2019,2\n"
        "1,India; Pakistan,Government of India,Government of Pakistan,2025,2\n"
        "2,Russia; Ukraine,Government of Russia (Soviet Union),Government of Ukraine,2025,2\n"
    )
    assert frozenset(("IND", "PAK")) in dyads
    result = scenarios.build_scenarios(
        dyads=dyads,
        last_conflict_year=2025,
        active_interstate={"RUS", "UKR"},
        markets=polymarket.markets([_search_payload()]),
        milex={"RUS": {"value": 7.1, "change5": 3.0}, "POL": {"value": 4.2, "change5": 2.0}},
        gpr={"RUS": {"ratio_12m": 1.5}},
        generated_at=NOW,
    )
    by_key = {s["key"]: s for s in result["scenarios"]}
    assert result["schema"] == scenarios.SCHEMA
    taiwan = by_key["china_taiwan"]
    assert taiwan["market_status"] == "matched"
    assert {c["kind"] for c in taiwan["components"]} == {"history", "expert", "market"}
    for key, item in by_key.items():
        h = item["horizons"]
        assert 0 < h["1m"]["p"] < h["1y"]["p"] < h["5y"]["p"] < h["10y"]["p"] < 1, key
        assert h["1y"]["low"] <= h["1y"]["p"] <= h["1y"]["high"], key
        assert item["calibration"] == "uncalibrated"
    nato = by_key["russia_nato"]
    roles = {a["iso3"]: a["role"] for a in nato["affected"]}
    assert roles["LTU"] == "frontline" and roles["LVA"] == "frontline"
    assert roles["RUS"] == "party" and roles["ITA"] == "ally" and roles["AUT"] == "ally"
    assert nato["indicator_factor"] > 1  # rising spending, risk index and an ongoing war
    assert by_key["ukraine_ceasefire"]["indicator_factor"] < 1
    assert by_key["india_pakistan"]["components"][0]["kind"] == "history"


def test_scenarios_without_optional_sources_still_build():
    result = scenarios.build_scenarios(
        dyads=None,
        last_conflict_year=None,
        active_interstate=set(),
        markets=None,
        milex={},
        gpr={},
        generated_at=NOW,
    )
    item = result["scenarios"][0]
    assert item["market_status"] == "unavailable"
    assert [c["kind"] for c in item["components"]] == ["expert", "official"]


def test_unhcr_displacement_and_eurostat_trend():
    rows = [
        {"coo_iso": "UKR", "coa_iso": "POL", "refugees": 900000, "asylum_seekers": "-"},
        {"coo_iso": "UKR", "coa_iso": "DEU", "refugees": 1100000, "asylum_seekers": 1000},
        {"coo_iso": "SYR", "coa_iso": "DEU", "refugees": 700000, "oip": 10},
        {"coo_iso": "UKR", "coa_iso": "UKR", "idps": 3700000},
    ]
    data = migration.displacement(rows, 2025)
    assert data["DEU"]["hosted"] == 1801010
    assert data["DEU"]["hosted_from"][0] == {"iso3": "UKR", "n": 1101000}
    assert data["UKR"]["abroad"] == 2001000 and data["UKR"]["idps"] == 3700000

    months = [f"2024-{m:02d}" for m in range(1, 13)] + [f"2025-{m:02d}" for m in range(1, 13)]
    payload = {
        "id": ["freq", "geo", "time"],
        "size": [1, 2, 24],
        "dimension": {
            "freq": {"category": {"index": {"M": 0}}},
            "geo": {"category": {"index": {"DE": 0, "EL": 1}}},
            "time": {"category": {"index": {m: i for i, m in enumerate(months)}}},
        },
        "value": {str(i): 100 for i in range(12)}
        | {str(i): 50 for i in range(12, 24)}
        | {str(24 + i): 10 for i in range(24)},
    }
    trend = migration.asylum_trend(migration.jsonstat_series(payload))
    assert trend["DEU"]["last12"] == 600 and trend["DEU"]["change"] == -0.5
    assert trend["GRC"]["change"] == 0.0


def test_trade_links_and_military_spending():
    codes = trade.reference_codes(
        {
            "results": [
                {"reporterCode": 251, "reporterCodeIsoAlpha3": "FRA"},
                {"reporterCode": 724, "reporterCodeIsoAlpha3": "ESP"},
                {"reporterCode": 276, "reporterCodeIsoAlpha3": "DEU"},
                {"reporterCode": 97, "reporterCodeIsoAlpha3": "EUR", "isGroup": True},
            ]
        }
    )
    assert codes == {251: "FRA", 724: "ESP", 276: "DEU"}
    responses = [
        {
            "data": [
                {"reporterCode": 724, "partnerCode": 0, "primaryValue": 400},
                {"reporterCode": 724, "partnerCode": 251, "primaryValue": 60},
                {"reporterCode": 724, "partnerCode": 276, "primaryValue": 40},
            ]
        },
        {
            "data": [
                {"reporterISO": "DEU", "partnerISO": "FRA", "partnerCode": 251, "primaryValue": 90}
            ]
        },
    ]
    links = trade.trade_links(trade.exports_by_partner(responses, codes))
    assert links["ESP"]["exports_to"][0] == {"iso3": "FRA", "share": 0.15}
    assert links["FRA"]["imports_from"][0] == {"iso3": "DEU", "share": 0.6}

    csv_text = "Entity,Code,Year,milex\n" + "\n".join(
        f"Poland,POL,{y},{1.8 + (y - 2015) * 0.3:.2f}" for y in range(2015, 2025)
    )
    summary = trade.milex_summary(trade.owid_series(csv_text))
    assert summary["POL"]["year"] == 2024 and summary["POL"]["change5"] == 1.5

    built = build_links(
        trade=links,
        trade_year=2024,
        displacement={"DEU": {"hosted": 1000, "year": 2025}},
        asylum=None,
        profiles={"DEU": {"population": {"value": 1_000_000, "year": 2024}}},
        generated_at=NOW,
    )
    assert built["countries"]["DEU"]["migration"]["hosted_per_1000"] == 1.0
    assert any(r["key"] == "channel" for r in built["routes"])


def test_short_markets_are_signals_and_inverse_markets_flip():
    markets = [
        {
            "question": "NATO x Russia military clash by December 31, 2026?",
            "slug": "a",
            "p": 0.15,
            "end": "2026-12-31",
            "volume": 4_000_000.0,
            "month_change": 0.05,
        },
        {
            "question": "Israel x Iran ceasefire continues through December 31?",
            "slug": "b",
            "p": 0.7,
            "end": "2026-12-31",
            "volume": 3_000_000.0,
            "month_change": -0.1,
        },
    ]
    result = scenarios.build_scenarios(
        dyads=None,
        last_conflict_year=None,
        active_interstate=set(),
        markets=markets,
        milex={},
        gpr={},
        generated_at=NOW,
    )
    by_key = {s["key"]: s for s in result["scenarios"]}
    nato = by_key["russia_nato"]
    assert nato["market_status"] == "no_match"  # 37 days is too short to annualise
    trend = next(i for i in nato["indicators"] if i["key"] == "market_trend")
    assert trend["direction"] == 1 and "15.0%" in trend["value"]
    iran = by_key["iran_strikes"]
    assert iran["market_candidates"][0]["inverse"] and iran["market_candidates"][0]["p"] == 0.3
    trend = next(i for i in iran["indicators"] if i["key"] == "market_trend")
    assert trend["direction"] == 1 and trend["value"].startswith("30.0%")


def test_scenario_tree_rises_over_time_and_branches_sum_to_one():
    from geointel.risk import scenario_tree

    result = scenario_tree.simulate("russia_nato", 0.03, 0.25, 0.1)
    yearly = [y["annual"] for y in result["yearly"]]
    assert yearly[-1] > yearly[0]  # capability rebuilds after a ceasefire
    assert abs(sum(b["weight"] for b in result["branches"]) - 1) < 1e-3
    assert result["p1y"] < result["p5y"] < result["p10y"] < 1
    firm = {b["ukraine"]: b for b in result["branches"] if b["us"] == "us_firm"}
    weak = {b["ukraine"]: b for b in result["branches"] if b["us"] == "us_weak"}
    assert weak["cease_early"]["p10y"] > firm["cease_early"]["p10y"]


def test_new_scenarios_and_combined_official_judgements():
    result = scenarios.build_scenarios(
        dyads=None,
        last_conflict_year=None,
        active_interstate=set(),
        markets=None,
        milex={},
        gpr={},
        generated_at=NOW,
    )
    by_key = {s["key"]: s for s in result["scenarios"]}
    for key in (
        "moldova_transnistria",
        "belarus_front",
        "serbia_kosovo",
        "venezuela_guyana",
        "turkey_greece",
        "sahel_coups",
        "us_guarantee",
    ):
        assert key in by_key, key
    official = next(c for c in by_key["russia_nato"]["components"] if c["kind"] == "official")
    assert len(official["sources"]) == 2 and official["low"] < official["annual"] < official["high"]
    assert "tree" in by_key["russia_nato"] and "tree" in by_key["russia_nato_war"]


def test_accuracy_scores_forecasts_after_thirty_days():
    from datetime import date

    from geointel.risk import accuracy

    day = {
        "scenarios": [
            {"key": "k", "title_ru": "К", "horizons": {"1m": {"p": 0.1}, "1y": {"p": 0.5}}}
        ]
    }
    early = accuracy.build({"2026-11-01": day}, date(2026, 11, 20))
    assert early["status"] == "collecting" and early["first_score_on"] == "2026-12-01"
    later = accuracy.build({"2026-11-01": day, "2026-11-20": day}, date(2026, 12, 2))
    assert later["status"] == "scoring" and later["overall"]["n"] == 1
    assert later["summary"]["k"]["brier"] == 0.01 and len(later["series"]["k"]) == 2


def test_metaculus_uses_history_when_latest_is_missing():
    from geointel.risk.sources import metaculus

    payload = {
        "results": [
            {
                "id": 9,
                "title": "Will X happen?",
                "question": {
                    "type": "binary",
                    "scheduled_close_time": "2027-06-01T00:00:00Z",
                    "aggregations": {
                        "recency_weighted": {"latest": None, "history": [{"centers": [0.3]}]}
                    },
                },
            }
        ]
    }
    assert metaculus.questions([payload])[0]["p"] == 0.3
    assert metaculus.diagnose(payload).startswith("ok=1")


def test_expert_panel_needs_a_reason():
    from geointel.risk.expert_panel import panel_component

    answers = [
        {"answers": [{"scenario": "k", "p1y": 0.04, "why": "troop build-up"}]},
        {"answers": [{"scenario": "k", "p1y": 0.01, "why": "deterrence"}]},
        {"answers": [{"scenario": "k", "p1y": 0.5, "why": ""}]},
    ]
    comp = panel_component("k", answers)
    assert comp["kind"] == "panel" and comp["annual"] == 0.02 and comp["high"] == 0.04
    assert panel_component("other", answers) is None


def test_signs_are_not_counted_twice():
    signs = {
        "EST": [
            {"key": "intel_warning", "status": "active", "lr": 1.3, "group": "intel"},
            {"key": "hybrid", "status": "active", "lr": 1.2, "group": "hybrid"},
            {"key": "ongoing_war", "status": "active", "lr": 1.2, "group": "intel"},
        ]
    }
    by_key = {s.key: s for s in scenarios.CATALOGUE}
    keys = {s["key"] for s in scenarios.scenario_signs(by_key["russia_nato"], signs, None, set())}
    assert keys == {"hybrid"}  # the judgement is pooled already; the war is in the prior
    assert scenarios.scenario_signs(by_key["us_guarantee"], signs, None, set()) == []


def test_telegram_digest():
    from datetime import date

    from geointel.risk import notify

    def scen(p):
        return {
            "scenarios": [
                {"key": "russia_nato", "title_ru": "Нападение", "horizons": {"1y": {"p": p}}}
            ]
        }

    signals = {
        "generated_at": "2026-11-25T05:00:00+00:00",
        "catalogue": [{"key": "hybrid", "label_ru": "Диверсии"}],
        "countries": {"EST": {"signs": [{"key": "hybrid", "status": "active", "value_ru": "x"}]}},
    }
    history = {"EST": [["2026-11-24", 1.0, []], ["2026-11-25", 1.2, ["hybrid"]]]}
    text = notify.digest(scen(0.06), scen(0.04), signals, history, date(2026, 11, 25))
    assert "4,0% → 6,0%" in text and "Эстония: Диверсии — x" in text
    quiet = notify.digest(scen(0.04), scen(0.04), {"countries": {}}, {}, date(2026, 11, 25))
    assert quiet is None  # Wednesday, nothing changed
    assert notify.send("x") is False  # no secrets in tests


def test_caucasus_and_middle_east_scenarios():
    by_key = {s.key: s for s in scenarios.CATALOGUE}
    for key in (
        "armenia_azerbaijan",
        "israel_hezbollah",
        "hormuz_reopening",
        "georgia_crisis",
        "iraq_strikes",
    ):
        assert key in by_key, key
    assert by_key["hormuz_reopening"].polarity == -1
    assert by_key["georgia_crisis"].risk == "political_crisis"
    assert len({s.key for s in scenarios.CATALOGUE}) == len(scenarios.CATALOGUE)
