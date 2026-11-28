import json
from datetime import date
from pathlib import Path

from geointel.risk.sources import polcrisis as pc

FIXTURE = Path(__file__).parent / "fixtures" / "polcrisis_raw.json"
UNIVERSE = frozenset({"PER", "NLD"})


def _resolve(name: str) -> str | None:
    return {"Peru": "PER", "Netherlands": "NLD"}.get(name)


def _build() -> dict:
    raw = json.loads(FIXTURE.read_text())
    return pc.build(raw, UNIVERSE, {}, _resolve, date(2026, 11, 28))


def _find(result: dict, iso3: str, component: str) -> list[str]:
    return [
        e["date"] for e in result["events"] if e["iso3"] == iso3 and e["component"] == component
    ]


def test_every_event_has_a_source_and_known_component():
    result = _build()
    assert result["events"]
    for event in result["events"]:
        assert event["component"] in pc.COMPONENTS
        assert event["source"] in pc.SOURCES and event["source_ref"]
        assert event["year"] == int(event["date"][:4])
        assert pc.FIRST_YEAR <= event["year"] <= pc.LAST_YEAR


def test_leader_exits_follow_the_schedule_rules():
    exits = _build()["events"]
    peru = {e["date"]: e for e in exits if e["iso3"] == "PER" and e["component"] == "leader_exit"}
    # resignation (P1534) counts; terms ending after elections or after a full term do not
    assert "2018-03-23" in peru and "resignation" in peru["2018-03-23"]["detail"]
    assert not {"2001-07-28", "2006-07-28", "2011-07-28", "2016-07-28"} & set(peru)
    # acting president (Merino) is not an exit; Vizcarra's removal comes once, from the list
    assert "2020-11-15" not in peru
    assert [d for d in peru if d.startswith("2020-11")] == ["2020-11-09"]
    assert peru["2020-11-09"]["source"] == "manual"


def test_monarch_exit_is_not_excused_by_a_parliamentary_election():
    result = _build()
    assert _find(result, "NLD", "leader_exit") == ["2013-04-30"]
    # prime ministers who left after general elections and a re-appointed PM are not events;
    # the governor of a constituent country is not a head of state
    details = " ".join(e["detail"] for e in result["events"])
    assert "Wim Kok" not in details and "Balkenende" not in details
    assert "Holiday" not in details


def test_snap_elections_from_wikidata_and_wikipedia():
    result = _build()
    dutch = _find(result, "NLD", "snap_election")
    # Wikidata snap type; "Early general elections" in the lead; Wikipedia snap-election list
    assert dutch == ["2003-01-22", "2006-11-22", "2010-06-09", "2012-09-12", "2025-10-29"]
    assert any("Background" in e["detail"] for e in result["events"] if e["date"] == "2010-06-09")
    # a postponed election, a lead about the previous snap election, no interval guessing
    assert "2021-03-17" not in dutch and "2023-11-22" not in dutch
    assert _find(result, "PER", "snap_election") == []


def test_snap_phrase_detection():
    assert pc.snap_in_intro("Snap parliamentary elections were held in X on 1 May.")
    assert pc.snap_in_intro("Elections were brought forward after the coalition collapsed.")
    assert pc.snap_in_intro("Early voting started on 1 May. The vote was on 5 May.") is None
    assert pc.snap_in_intro("General elections were held in X on 5 May.") is None
    assert pc.snap_in_intro("Elections were held after the death of President Y.")
    assert pc.snap_in_intro("They followed the death in an air crash of incumbent President Z.")
    assert pc.background_section("Lead.\n== Background ==\nEarly polls.\n== Results ==\nX") == (
        "Early polls."
    )
    assert pc.snap_in_intro("It was originally scheduled for May but was delayed.") is None
    assert pc.snap_in_intro("They were held following the resignation of the government.") is None


def test_rotation_and_short_caretaker_terms_are_not_exits():
    offices = {
        "B": {"iso3": {"BTN"}, "roles": {"head_of_government"}, "label": "Prime Minister"},
        "L": {"iso3": {"LTU"}, "roles": {"head_of_government"}, "label": "Prime Minister"},
    }

    def term(office, person, start, end):
        return {
            "office": office,
            "person": person,
            "name": person,
            "start": date.fromisoformat(start),
            "end": date.fromisoformat(end),
            "end_precision": 11,
            "causes": set(),
            "nature": set(),
            "statement": person,
        }

    terms = [
        term("B", "Zimba", "2000-07-20", "2001-08-08"),  # yearly rotation 1998–2008
        term("B", "Tobgay", "2013-07-27", "2016-03-01"),  # outside the rotation period
        term("L", "Sadzius", "2025-08-04", "2025-09-25"),  # 52-day caretaker
    ]
    exits = pc.leader_exits(terms, offices, [])
    assert [(e["iso3"], e["date"]) for e in exits] == [("BTN", "2016-03-01")]


def test_full_term():
    assert pc.full_term(date(2011, 9, 1), date(2017, 8, 31))
    assert not pc.full_term(date(2016, 7, 28), date(2018, 3, 23))
    assert not pc.full_term(None, date(2018, 3, 23))


def test_coups_emergencies_and_impeachments():
    result = _build()
    assert _find(result, "PER", "coup") == ["2000-10-29"]  # conspiracy and 1992 excluded
    assert result["unresolved"]["cline_countries"] == 1
    assert _find(result, "NLD", "emergency") == ["2015-06-01"]
    assert _find(result, "PER", "impeachment") == ["2020-11-09"]


def test_coverage_years_and_shape():
    result = _build()
    assert result["covered"] == ["NLD", "PER"]
    assert result["years"]["PER"] == sorted(set(result["years"]["PER"]))
    assert 2018 in result["years"]["PER"] and 2013 in result["years"]["NLD"]
    assert result["version"] == 1 and result["first_year"] == 2000 and result["last_year"] == 2025


def test_coverage_needs_known_leaders():
    raw = json.loads(FIXTURE.read_text())
    raw["holders"] = [h for h in raw["holders"] if not h["office"]["value"].endswith("/Q1")]
    result = pc.build(raw, UNIVERSE, {}, _resolve, date(2026, 11, 28))
    assert "PER" not in result["covered"] and "NLD" in result["covered"]


def test_recall_against_reference_sets():
    quality = _build()["quality"]["recall_vs_reference"]
    archigos = quality["leader_exit_vs_archigos_2000_2015"]
    assert archigos["reference"] == 2  # irregular / ill-health exits 2000–2015 only
    nelda = quality["snap_election_vs_nelda_2000_2010"]
    # early (by note) once per round pair; late and note-less elections are not in the reference
    assert nelda == {"reference": 2, "found": 1, "recall": 0.5, "missed": ["PER 2001-04-08"]}


def test_sample_is_reproducible_and_checks_are_applied():
    events = _build()["events"]
    first = pc.sample(events, size=5)
    assert first == pc.sample(list(reversed(events)), size=5)
    checks = [
        {**{k: first[0][k] for k in ("iso3", "date", "component", "detail")}, "verdict": "ok"},
        {
            **{k: first[1][k] for k in ("iso3", "date", "component", "detail")},
            "verdict": "error",
            "note": "did not happen",
        },
    ]
    quality = pc.apply_checks(events, checks)
    assert quality["sample_size"] == 2 and quality["errors"] == 1 and quality["error_rate"] == 0.5
    assert sum(e["checked"] for e in events) == 2


def test_quality_threshold_is_reported():
    quality = _build()["quality"]
    assert quality["thresholds"] == {"max_error_rate": 0.10, "min_recall": 0.70}
    assert quality["passed"] is False  # no checked sample in the fixture
