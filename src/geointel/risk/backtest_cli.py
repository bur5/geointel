"""``python -m geointel.risk backtest-base``: download the histories the base model uses and
run the time machine (docs/backtest-rules.md). Data loading lives here, never in
``backtest_base`` (the model side reads only what it is given)."""

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

SOURCES = "ucdp_acd,ucdp_term,coups,protests,usgs,tsunami,worldbank,fts,regimes"


def _experiment_data(raw_dir: Path) -> tuple[dict, dict]:
    """GED country-year deaths (experiment B) and strategic rivalries (experiment C).
    Failures leave the experiment out; they never stop the run."""
    import httpx

    from geointel.risk.sources import rivalries, ucdp_ged

    violence: dict = {}
    rivals: dict = {}
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        try:
            urls = ucdp_ged.links(client.get(ucdp_ged.DOWNLOADS).text)
            text = ucdp_ged.read_zip_csv(client.get(urls["ged"]).content)
            violence = ucdp_ged.country_year(text)
            print(f"[backtest] GED country-years: {len(violence)} countries from {urls['ged']}")
        except Exception as exc:  # noqa: BLE001
            print(f"[backtest] GED for experiment B failed: {type(exc).__name__} {exc}")
        try:
            for name, url in (("riv.rda", rivalries.DATA), ("states.rda", rivalries.STATES)):
                (raw_dir / name).write_bytes(client.get(url).content)
            rivals = rivalries.load(str(raw_dir / "riv.rda"), str(raw_dir / "states.rda"))
            print(f"[backtest] rivalries: {len(rivals)} countries")
        except Exception as exc:  # noqa: BLE001
            print(f"[backtest] rivalries for experiment C failed: {type(exc).__name__} {exc}")
    return violence, rivals


def run(out: Path, raw_dir: Path) -> int:
    from geointel.risk import MODEL_VERSION, backtest_base
    from geointel.risk.__main__ import load_histories
    from geointel.risk.countries import universe
    from geointel.risk.fetch import fetch_all
    from geointel.risk.sources import outlook
    from geointel.risk.taxonomy import EVENT_TYPES

    os.environ["GEOINTEL_SOURCES"] = SOURCES
    manifest = fetch_all(raw_dir)
    print("[backtest] fetched:", {k: v["status"] for k, v in manifest.items()})
    year = datetime.now(UTC).year
    histories, _sources, _events = load_histories(raw_dir, year, {})
    wanted = {k: h for k, h in histories.items() if k in backtest_base.LAG and h is not None}
    regime_series = {}
    regimes = manifest.get("regimes") or {}
    if regimes.get("status") == "ok":
        regime_series = outlook.owid_regime_series((raw_dir / regimes["file"]).read_text())
    persistent = {spec.key: spec.persistent_state for spec in EVENT_TYPES}
    first_years = {c.iso3: c.first_year for c in universe()}
    holdout = os.environ.get("GEOINTEL_HOLDOUT_APPROVED") == "1"
    termination = {}
    term = manifest.get("ucdp_term") or {}
    if term.get("status") == "ok":
        from geointel.risk.sources import ucdp_term

        termination = ucdp_term.episodes((raw_dir / term["file"]).read_text("utf-8-sig"))
        print(f"[backtest] conflict endings: {len(termination)} countries, {term.get('version')}")
    violence, rivals = _experiment_data(raw_dir)
    result = backtest_base.run(
        wanted, first_years, persistent, regime_series, holdout, termination, violence, rivals
    )
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        commit = ""
    result.update(
        {
            "schema": "geointel-backtest-base-v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "model_version": MODEL_VERSION,
            "commit": commit,
            "holdout_opened": holdout,
            "sources": {k: v.get("version") for k, v in manifest.items()},
        }
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False))
    for key, item in result["types"].items():
        for period, states in item["periods"].items():
            for state, s in states.items():
                print(
                    f"[backtest] {key} {period} {state}: n={s['n']} events={s['events']} "
                    f"brier={s['brier']} BSS vs reference={s.get('bss_vs_base')} "
                    f"vs world={s['bss_vs_world']} vs last year={s['bss_vs_last_year']}"
                )
    for label, periods in (result.get("coup_variants") or {}).items():
        for period, s in periods.items():
            print(
                f"[backtest] coups [{label}] {period}: BSS vs world={s['bss_vs_world']} "
                f"brier={s['brier']} log={s['log_score']} auc_pr={s['auc_pr']}"
            )
    for label, periods in (result.get("conflict_variants") or {}).items():
        for period, states in periods.items():
            for state, s in states.items():
                print(
                    f"[backtest] conflict [{label}] {period} {state}: n={s['n']} "
                    f"events={s['events']} brier={s['brier']} log={s['log_score']}"
                )
    for label, periods in (result.get("termination_variants") or {}).items():
        for period, s in periods.items():
            print(
                f"[backtest] onset [{label}] {period}: n={s['n']} events={s['events']} "
                f"BSS vs world={s['bss_vs_world']} brier={s['brier']} log={s['log_score']}"
            )
    exps = result.get("experiments") or {}
    for key, periods in (exps.get("site_lag") or {}).items():
        for period, states in periods.items():
            for state, s in states.items():
                print(
                    f"[backtest] site-lag {key} {period} {state}: n={s['n']} events={s['events']} "
                    f"brier={s['brier']} BSS vs reference={s.get('bss_vs_base')}"
                )
    for key, periods in (exps.get("site_lag_onsets") or {}).items():
        for period, items in periods.items():
            print(
                f"[backtest] site-lag onsets {key} {period}: {len(items)}, repeats "
                f"{sum(1 for x in items if x['repeat'])}"
            )
    for name in ("A_continuation_world", "B_subthreshold_violence", "C_rivalries"):
        for period, r in (exps.get(name) or {}).items():
            print(
                f"[backtest] experiment {name} {period}: current brier={r['current']['brier']} "
                f"vs ref={r['current'].get('bss_vs_base')}; variant brier={r['variant']['brier']} "
                f"vs ref={r['variant'].get('bss_vs_base')}; variant vs current="
                f"{r['variant_vs_current']}"
            )
    for period, d in result["danger"].items():
        print(
            f"[backtest] danger {period}: levels={d['levels']} violations="
            f"{d.get('order_violations')} bands={d.get('bands')}"
        )
        print(f"[backtest] danger {period} events at levels 1-2: {d.get('events_at_levels_1_2')}")
    for key, periods in (result.get("onset_lists") or {}).items():
        for period, items in periods.items():
            repeats = [f"{x['iso3']}{x['year']}" for x in items if x["repeat"]]
            print(
                f"[backtest] onsets {key} {period}: {len(items)}, repeats {len(repeats)}: "
                + " ".join(f"{x['iso3']}{x['year']}" for x in items)
            )
    return 0
