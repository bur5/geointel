from pathlib import Path

from geointel.risk import backtest_base as bt
from geointel.risk.model import TypeHistory
from geointel.risk.taxonomy import EventType


def _history(events, end=2025, key=EventType.COUP_ATTEMPT):
    return TypeHistory(key, "test", 1990, end, {k: frozenset(v) for k, v in events.items()})


COUNTRIES = {c: None for c in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III")}
EVENTS = {"AAA": {1995, 2003, 2010, 2016}, "BBB": {2001}, "CCC": set(), "DDD": {1999, 2012}}


def test_as_of_cuts_the_future():
    h = bt.as_of(_history(EVENTS), 2005)
    assert h.end_year == 2005
    assert h.years_with_event["AAA"] == frozenset({1995, 2003})


def test_poisoned_future_records_change_nothing():
    clean = _history(EVENTS, end=2030)
    poisoned = _history(
        {**EVENTS, "AAA": EVENTS["AAA"] | {2028, 2029, 2030}, "CCC": {2030}}, end=2030
    )
    for year in (2005, 2015, 2025):
        a = bt.forecasts(clean, COUNTRIES, False, year, 2)
        b = bt.forecasts(poisoned, COUNTRIES, False, year, 2)
        assert a == b
        assert bt.references(clean, COUNTRIES, year, 2) == bt.references(
            poisoned, COUNTRIES, year, 2
        )


def test_persistent_two_step_and_outcomes():
    conflict = _history(
        {"AAA": set(range(2000, 2026)), "BBB": {2010}}, key=EventType.INTERNAL_ARMED_CONFLICT
    )
    fc = bt.forecasts(conflict, COUNTRIES, True, 2020, 2)
    assert fc["AAA"]["state"] == "continuation" and fc["AAA"]["p"] > 0.5
    assert fc["BBB"]["state"] == "onset" and fc["BBB"]["p"] < 0.2
    assert bt.outcome(conflict, "AAA", 2020) == 1 and bt.outcome(conflict, "AAA", 2027) is None


def test_run_and_danger_check_shapes():
    conflict = _history(
        {"AAA": set(range(1995, 2026)), "BBB": {2010, 2017}}, key=EventType.INTERNAL_ARMED_CONFLICT
    )
    result = bt.run(
        {EventType.INTERNAL_ARMED_CONFLICT: conflict},
        COUNTRIES,
        {EventType.INTERNAL_ARMED_CONFLICT: True},
    )
    assert "holdout" not in result["periods"]
    tuning = result["types"]["internal_armed_conflict"]["periods"]["tuning"]
    assert tuning["continuation"]["n"] > 0 and tuning["onset"]["n"] > 0
    assert 4 in result["danger"]["tuning"]["levels"]


def test_model_code_reads_no_files_or_network():
    text = Path(bt.__file__).read_text()
    for forbidden in ("open(", "httpx", "requests", "urlopen", "read_text("):
        assert forbidden not in text


def test_coup_variants_are_reported():
    coups = _history(EVENTS)
    result = bt.run({EventType.COUP_ATTEMPT: coups}, COUNTRIES, {EventType.COUP_ATTEMPT: False})
    assert set(bt.COUP_VARIANTS) <= set(result["coup_variants"])


def test_offset_model_keeps_base_when_features_say_nothing():
    records = []
    for year in range(1992, 2016):
        for i in range(40):
            records.append(
                {
                    "iso3": f"C{i}",
                    "year": year,
                    "state": "all",
                    "p": 0.05,
                    "y": int((i + year) % 20 == 0),
                    "x": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    "world": 0.05,
                    "last_year": 0.05,
                }
            )
    out = bt.offset_records(records, 2, 2000)
    assert out and all(abs(r["p"] - 0.05) < 0.01 for r in out)


def test_world_cap_lets_own_record_count_more():
    from geointel.risk.model import assess_type

    events = {c: {2000 + i} for i, c in enumerate(COUNTRIES)}
    events["AAA"] = {2000, 2018}
    history = _history(events)
    strong = {r.iso3: r.horizons["1y"].p for r in assess_type(history, COUNTRIES, False)}
    capped = {r.iso3: r.horizons["1y"].p for r in assess_type(history, COUNTRIES, False, None, 2.0)}
    assert capped["AAA"] > strong["AAA"]
    assert capped["AAA"] > capped["CCC"]


def test_lull_year_counts_as_continuation():
    from geointel.risk.model import transition_counts

    flicker = _history({"AAA": {2000, 2002, 2004, 2006}}, key=EventType.INTERNAL_ARMED_CONFLICT)
    onset0, _ = transition_counts(flicker, "AAA", None, gap=0)
    onset1, cont1 = transition_counts(flicker, "AAA", None, gap=1)
    assert onset1.successes < onset0.successes
    assert cont1.trials > 0


def test_primary_reference_is_the_rate_for_the_known_state():
    conflict = _history(
        {"AAA": set(range(1995, 2026)), "BBB": {2010, 2011, 2017, 2018}},
        key=EventType.INTERNAL_ARMED_CONFLICT,
    )
    records = bt.run_type(EventType.INTERNAL_ARMED_CONFLICT, conflict, COUNTRIES, True, [2020])
    for r in records:
        assert r["base"] == r["last_year"]  # onset among peace, continuation among war
        assert r["base"] != r["world"]
    coups = bt.run_type(EventType.COUP_ATTEMPT, _history(EVENTS), COUNTRIES, False, [2020])
    assert all(r["base"] == r["world"] for r in coups)
    summary = bt.summarise(records)
    assert summary["bss_vs_base"] is not None


def test_two_way_interval_contains_point():
    records = [
        {"iso3": c, "year": y, "p": 0.2, "y": int((y + i) % 5 == 0), "base": 0.1}
        for i, c in enumerate(COUNTRIES)
        for y in range(2000, 2016)
    ]
    point, lo, hi = bt.skill_interval(records, "base", samples=200)
    assert lo <= point <= hi


def test_onset_lists_mark_repeats_and_danger_bands():
    conflict = _history(
        {"AAA": {2016, 2017, 2018}, "BBB": {2018}}, key=EventType.INTERNAL_ARMED_CONFLICT
    )
    result = bt.run(
        {EventType.INTERNAL_ARMED_CONFLICT: conflict},
        COUNTRIES,
        {EventType.INTERNAL_ARMED_CONFLICT: True},
    )
    items = result["onset_lists"]["internal_armed_conflict"]["validation"]
    aaa = [x for x in items if x["iso3"] == "AAA"]
    assert aaa[0]["year"] == 2016 and not aaa[0]["repeat"] and aaa[1]["repeat"]
    danger = result["danger"]["validation"]
    assert "bands" in danger and isinstance(danger["order_violations"], list)
    assert all(e["level"] <= 2 for e in danger["events_at_levels_1_2"])
