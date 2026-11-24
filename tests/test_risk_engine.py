import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from geointel.risk.__main__ import main
from geointel.risk.betamath import beta_cdf, beta_ppf
from geointel.risk.countries import resolve_country_name, resolve_usgs_place, universe
from geointel.risk.model import (
    BetaPrior,
    Counts,
    TypeHistory,
    active_at_end,
    assess_type,
    fit_prior,
    onset_within,
    posterior,
)
from geointel.risk.snapshot import build_snapshot, diff_snapshots
from geointel.risk.sources import coups, ucdp_acd, usgs
from geointel.risk.taxonomy import EventType, Question

FIXTURES = Path(__file__).parent / "fixtures" / "risk"
HORIZON_ORDER = ("1m", "1y", "5y", "10y")


def test_beta_helpers_match_known_values():
    assert beta_cdf(0.3, 1, 1) == pytest.approx(0.3)
    assert beta_ppf(0.3, 1, 1) == pytest.approx(0.3, abs=1e-9)
    assert beta_cdf(0.5, 3, 3) == pytest.approx(0.5)
    for q in (0.05, 0.5, 0.95):
        assert beta_cdf(beta_ppf(q, 2.5, 40), 2.5, 40) == pytest.approx(q, abs=1e-8)


def test_universe_and_name_resolution():
    codes = {c.iso3 for c in universe()}
    assert len(codes) == 196
    assert {"UKR", "RUS", "TWN", "PSE", "XKX", "SSD"} <= codes
    assert resolve_country_name("Russia (Soviet Union)") == "RUS"
    assert resolve_country_name("Government of DR Congo (Zaire)") == "COD"
    assert resolve_country_name("Hyderabad") is None
    assert resolve_usgs_place("100 km W of Adak, Alaska") == "USA"
    assert resolve_usgs_place("near the coast of Ecuador") == "ECU"
    assert resolve_usgs_place("central Mid-Atlantic Ridge") is None


def test_empirical_bayes_shrinks_but_preserves_ordering():
    counts = [Counts(0, 30)] * 150 + [Counts(15, 30)] * 30 + [Counts(30, 30)] * 10
    prior = fit_prior(counts)
    assert 0 < prior.a / (prior.a + prior.b) < 0.5
    none = posterior(prior, Counts(0, 30))
    many = posterior(prior, Counts(25, 30))
    assert 0 < none.mean < many.mean < 1
    assert none.low <= none.mean <= none.high


def test_horizon_formulas_are_consistent():
    values = [onset_within(0.1, h) for h in (1 / 12, 1, 5, 10)]
    assert values == sorted(values)
    assert onset_within(0.1, 1) == pytest.approx(0.1)
    stationary = 0.05 / (0.05 + 0.2)
    # Started active: decays towards a stationary share, never below it.
    assert active_at_end(0.05, 0.8, 1 / 12) > active_at_end(0.05, 0.8, 1) > stationary * 0.9


def _history(years, persistent_half_life=10.0):
    return TypeHistory(
        event_type=EventType.INTERNAL_ARMED_CONFLICT,
        source="test",
        start_year=1990,
        end_year=2025,
        years_with_event={k: frozenset(v) for k, v in years.items()},
        half_life_years=persistent_half_life,
    )


def test_assess_persistent_type_distinguishes_active_and_peaceful_states():
    history = _history(
        {
            "AAA": set(range(1990, 2026)),
            "BBB": set(range(1995, 2005)),
            **{f"Z{i:02d}": set() for i in range(40)},
        }
    )
    countries = {"AAA": None, "BBB": None, "CCC": None, **{f"Z{i:02d}": None for i in range(40)}}
    results = {r.iso3: r for r in assess_type(history, countries, persistent=True)}
    assert results["AAA"].question is Question.ACTIVE_AT_END and results["AAA"].active
    assert results["BBB"].question is Question.ONSET_WITHIN and not results["BBB"].active
    assert results["BBB"].horizons["1y"].p > results["CCC"].horizons["1y"].p > 0
    for item in results.values():
        for horizon in item.horizons.values():
            assert 0 <= horizon.low <= horizon.p <= horizon.high <= 1
        if item.question is Question.ONSET_WITHIN:
            ps = [item.horizons[h].p for h in HORIZON_ORDER]
            assert ps == sorted(ps)


def test_exposure_respects_independence_year():
    history = _history({"SSD": set(range(2011, 2026))})
    countries = {"SSD": 2011, **{f"Z{i:02d}": None for i in range(20)}}
    (ssd,) = [r for r in assess_type(history, countries, True) if r.iso3 == "SSD"]
    assert ssd.exposure_years == 15 and ssd.event_years == 15


def test_ucdp_acd_parser():
    internal, interstate = ucdp_acd.parse((FIXTURES / "ucdp_acd_sample.csv").read_text())
    assert internal.years_with_event["MLI"] == {2021, 2022, 2023}
    assert internal.years_with_event["COL"] == {1995}
    assert internal.unresolved_labels == 2  # "Testland internal", "Hyderabad"
    assert interstate.years_with_event["RUS"] == {2022, 2023}
    assert interstate.years_with_event["UKR"] == {2022, 2023}
    assert internal.end_year == interstate.end_year == 2023


def test_coup_parser_uses_complete_years_only():
    history = coups.parse((FIXTURES / "coups_sample.txt").read_text(), reference_year=2026)
    assert history.years_with_event["MLI"] == {2020, 2021}
    assert history.years_with_event["TUR"] == {2016}
    assert history.end_year == 2025
    assert history.unresolved_labels == 1  # Atlantis
    assert "GIN" not in history.years_with_event  # before the window


def test_usgs_parser():
    history = usgs.parse((FIXTURES / "usgs_sample.csv").read_text(), reference_year=2026)
    assert history.years_with_event["JPN"] == {2011, 2016}
    assert history.years_with_event["TUR"] == {2023}
    assert history.years_with_event["FJI"] == {2020}
    assert "CHL" not in history.years_with_event  # below M6.5 or incomplete year
    assert history.unresolved_labels == 1
    assert history.half_life_years is None


def _sources():
    return [{"key": "test", "name": "fixture", "status": "ok"}]


def test_snapshot_marks_missing_and_unmodeled_types_unavailable():
    internal, interstate = ucdp_acd.parse((FIXTURES / "ucdp_acd_sample.csv").read_text())
    histories = {
        EventType.INTERNAL_ARMED_CONFLICT: internal,
        EventType.INTERSTATE_CONFLICT: interstate,
        EventType.COUP_ATTEMPT: None,
    }
    snapshot = build_snapshot(histories, _sources(), generated_at=datetime(2026, 1, 1, tzinfo=UTC))
    types = {t["key"]: t for t in snapshot["event_types"]}
    assert types["internal_armed_conflict"]["available"]
    assert not types["coup_attempt"]["available"]
    assert not types["mass_protest"]["modeled"] and not types["mass_protest"]["available"]
    countries = {c["iso3"]: c for c in snapshot["countries"]}
    assert len(countries) == 196
    mali = countries["MLI"]["risks"]
    assert "coup_attempt" not in mali  # unavailable, never zero
    assert mali["internal_armed_conflict"]["question"] == "active_at_end"
    assert countries["UKR"]["risks"]["interstate_conflict"]["active"] is True
    json.dumps(snapshot)


def test_diff_reports_material_changes_only():
    internal, _ = ucdp_acd.parse((FIXTURES / "ucdp_acd_sample.csv").read_text())
    histories = {EventType.INTERNAL_ARMED_CONFLICT: internal}
    first = build_snapshot(histories, _sources())
    second = json.loads(json.dumps(first))
    risk = next(c for c in second["countries"] if c["iso3"] == "MLI")["risks"]
    risk["internal_armed_conflict"]["horizons"]["1y"]["p"] -= 0.1
    changes = diff_snapshots(second, first)
    assert len(changes) == 1
    assert changes[0]["iso3"] == "MLI" and changes[0]["horizon"] == "1y"
    assert changes[0]["delta"] == pytest.approx(0.1, abs=1e-6)


def test_cli_build_with_partial_sources(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "ucdp_acd.bin").write_bytes((FIXTURES / "ucdp_acd_sample.csv").read_bytes())
    (raw / "usgs.csv").write_bytes((FIXTURES / "usgs_sample.csv").read_bytes())
    manifest = {
        "ucdp_acd": {"status": "ok", "file": "ucdp_acd.bin", "version": "25.1", "url": "x"},
        "usgs": {"status": "ok", "file": "usgs.csv", "url": "y"},
        "coups": {"status": "failed", "errors": ["HTTP 404"]},
    }
    (raw / "manifest.json").write_text(json.dumps(manifest))
    out = tmp_path / "site" / "risk.json"
    assert main(["build", "--raw-dir", str(raw), "--out", str(out)]) == 0
    snapshot = json.loads(out.read_text())
    available = {t["key"] for t in snapshot["event_types"] if t["available"]}
    assert available == {"internal_armed_conflict", "interstate_conflict", "major_earthquake"}
    status = {s["key"]: s["status"] for s in snapshot["sources"]}
    assert status == {"ucdp_acd": "ok", "coups": "failed", "usgs": "ok"}
    assert main(["build", "--raw-dir", str(raw), "--out", str(out), "--previous", str(out)]) == 0
    assert json.loads(out.read_text())["changes"] == []


def test_prior_fallback_when_no_data():
    assert fit_prior([]) == BetaPrior(0.5, 10.0)
