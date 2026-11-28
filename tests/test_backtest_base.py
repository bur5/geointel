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
