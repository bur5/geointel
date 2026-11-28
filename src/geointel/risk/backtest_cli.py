"""``python -m geointel.risk backtest-base``: download the histories the base model uses and
run the time machine (docs/backtest-rules.md). Data loading lives here, never in
``backtest_base`` (the model side reads only what it is given)."""

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

SOURCES = "ucdp_acd,coups,protests,usgs,tsunami,worldbank,fts,regimes"


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
    result = backtest_base.run(wanted, first_years, persistent, regime_series, holdout)
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
                    f"BSS vs world={s['bss_vs_world']} vs last year={s['bss_vs_last_year']}"
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
    for period, d in result["danger"].items():
        print(f"[backtest] danger {period}: order_ok={d['order_ok']} band={d['band_level3']}")
    return 0
