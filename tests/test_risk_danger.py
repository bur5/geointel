from geointel.risk.danger import apply_danger, country_danger, lower_median, type_level


def _country(iso3="AAA", risks=None, us=None, uk=None, **extra):
    base = {
        "iso3": iso3,
        "risks": risks or {},
        "advisory": {"level": us, "summary": ""} if us else None,
        "advisory_uk": {"level": uk, "restrictions": []} if uk else None,
    }
    base.update(extra)
    return base


def _risk(p1y, p1m=0.0, active=False):
    return {"active": active, "horizons": {"1m": {"p": p1m}, "1y": {"p": p1y}}}


def test_thresholds_by_class():
    assert type_level("internal_armed_conflict", 0.013) == 1
    assert type_level("internal_armed_conflict", 0.03) == 2
    assert type_level("internal_armed_conflict", 0.22) == 4
    assert type_level("coup_attempt", 0.2) == 3
    assert type_level("economic_crisis", 0.9) == 2  # class C never above 2


def test_hazards_do_not_raise_country_level():
    d = country_danger(_country(risks={"tropical_cyclone": _risk(0.9), "flood": _risk(0.8)}))
    assert d["level"] == 1
    assert {x["risk"] for x in d["drivers"]} == {"tropical_cyclone", "flood"}
    assert all(x["regional"] for x in d["drivers"])


def test_war_is_a_fact_and_abroad_is_lower():
    war = {"interstate_conflict": {"active": True}}
    assert country_danger(_country("RUS", war), intensity={"interstate": 2})["level"] == 4
    assert country_danger(_country("USA", war), intensity={"interstate": 2})["level"] == 2
    minor_internal = {"internal_armed_conflict": {"active": True}}
    assert country_danger(_country("IND", minor_internal), intensity={"internal": 1})["level"] == 2


def test_ministries_raise_one_step_only_and_never_lower():
    calm = _country(us=4, uk=4)
    d = country_danger(calm)
    assert d["model_level"] == 1 and d["level"] == 2 and d["raised_by_ministries"]
    assert d["divergence"] == 3
    war = _country("RUS", {"interstate_conflict": {"active": True}}, us=1, uk=1)
    assert country_danger(war, intensity={"interstate": 2})["level"] == 4


def test_lower_median_ignores_single_strict_ministry():
    assert lower_median([1, 1, 4]) == 1
    assert lower_median([2, 4]) == 2
    assert lower_median([]) is None


def test_monthly_spike_counts():
    d = country_danger(_country(risks={"coup_attempt": _risk(0.02, p1m=0.02)}))
    assert d["level"] == 3  # 2% a month ≈ 24% a year


def test_trend_is_separate_from_level():
    d = country_danger(_country(), alert={"ratio": 2.0, "risk": "coup_attempt"})
    assert d["level"] == 1 and d["trend"]["direction"] == "up"


def test_foreigner_risks_from_advisory_text():
    c = _country(us=4)
    c["advisory"]["summary"] = "Risk of wrongful detention and terrorism."
    keys = [f["key"] for f in country_danger(c)["foreigners"]]
    assert keys == ["detention", "terrorism"]


def test_apply_danger_histogram():
    snapshot = {"countries": [_country("AAA"), _country("BBB", us=4, uk=4)]}
    signals = {"countries": {}}
    hist = apply_danger(snapshot, signals)
    assert hist[1] == 1 and hist[2] == 1
    assert signals["danger_scale"]["hazard_cap"] == 1


def test_coup_group_shrinkage_lowers_stable_democracies():
    from geointel.risk.model import TypeHistory, assess_type
    from geointel.risk.taxonomy import EventType

    years = {}
    countries = {}
    groups = {}
    for i in range(12):
        countries[f"D{i:02d}"] = None
        groups[f"D{i:02d}"] = "3|none20"
    for i in range(12):
        code = f"A{i:02d}"
        countries[code] = None
        groups[code] = "1|coup20"
        years[code] = frozenset({1995 + i, 2010 + i % 10})
    history = TypeHistory(
        event_type=EventType.COUP_ATTEMPT,
        source="t",
        start_year=1990,
        end_year=2025,
        years_with_event={k: v for k, v in years.items()},
    )
    world = {r.iso3: r for r in assess_type(history, countries, False)}
    grouped = {r.iso3: r for r in assess_type(history, countries, False, groups)}
    assert grouped["D00"].horizons["10y"].p < world["D00"].horizons["10y"].p
    assert grouped["A00"].horizons["1y"].p >= world["A00"].horizons["1y"].p * 0.9


def test_every_scenario_has_a_resolution_source():
    from datetime import date

    from geointel.risk.resolution import SOURCES, scenario_resolution
    from geointel.risk.scenarios import CATALOGUE

    for scenario in CATALOGUE:
        res = scenario_resolution(scenario.key, date(2026, 11, 27))
        assert res["source_ru"] and res["source_en"], scenario.key
        assert res["window"]["1y"]["to"] == "2027-11-27"
        assert scenario.event_ru and scenario.event_en
    assert set(SOURCES) == {s.key for s in CATALOGUE}


def test_every_event_type_has_a_resolution_rule():
    from geointel.risk.taxonomy import EVENT_TYPES

    for spec in EVENT_TYPES:
        assert spec.resolution_ru and spec.resolution_en, spec.key


def test_conflict_onset_probability_gives_at_most_level_3():
    d = country_danger(_country("AZE", {"internal_armed_conflict": _risk(0.28)}))
    assert d["level"] == 3


def test_regional_median_lifts_country_to_4_at_most():
    from geointel.risk.danger import apply_regional

    d = apply_regional(
        {"level": 2},
        {"level_median": 5, "level_max": 5, "max_regions": [], "max_population_share": 0.6},
    )
    assert d["level"] == 4 and d["regional"]["median"] == 5


def test_foreigner_tags_whole_words_and_elevated_crime_health():
    from geointel.risk.danger import foreigner_risks

    plain = {
        "advisory": {
            "summary": "The ministry determines and examines health and crime information "
            "for travellers; petty crime exists as everywhere."
        }
    }
    assert foreigner_risks(plain) == []
    serious = {
        "advisory": {
            "summary": "Violent crime is common. Landmines remain near the border. "
            "A cholera outbreak was reported. Terrorists may attack."
        }
    }
    keys = {x["key"] for x in foreigner_risks(serious)}
    assert keys == {"crime", "mines", "health", "terrorism"}


def test_fighting_abroad_from_deaths_on_home_soil():
    from geointel.risk.danger import fought_abroad, war_level

    assert fought_abroad("USA", None)  # no GED: the fallback list
    assert not fought_abroad("RUS", None)
    assert fought_abroad("RUS", {"RUS": 3.0}) and not fought_abroad("RUS", {"RUS": 400.0})
    assert not fought_abroad("USA", {"USA": 30.0})
    assert war_level("ISR", "interstate", 2, abroad=False) == 4
    assert war_level("ISR", "interstate", 2, abroad=True) == 2


def test_inform_category_not_index_sets_level():
    from geointel.risk.danger import severity_level

    assert severity_level({"score": 4.2, "category": "3"}) == 2  # medium crisis
    assert severity_level({"score": 7.1, "category": "4"}) == 3
    assert severity_level({"score": 9.5, "category": "5"}) == 3
    assert severity_level({"score": 6.5, "category": ""}) == 3  # no category: index ≥ 6
    assert severity_level(None) == 2
