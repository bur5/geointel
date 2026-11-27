"""``python -m geointel.risk train``: download what the trained models need, run the
pre-registered forward validation and write ``trained.json``."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

from geointel.risk import trained
from geointel.risk.countries import universe
from geointel.risk.model import TypeHistory
from geointel.risk.sources import protests

WB = {
    "gdppc": "NY.GDP.PCAP.KD",
    "imr": "SP.DYN.IMRT.IN",
    "pop": "SP.POP.TOTL",
}
TOPO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json"


def mass_mobilization(client: httpx.Client) -> tuple[TypeHistory | None, str]:
    """Mass Mobilization (Clark & Regan, CC0): years with a protest of 10,000+ people."""
    chosen = protests.pick_file(client.get(protests.DATASET, timeout=60).json())
    if not chosen:
        return None, "no data file in the dataset"
    payload = protests.parse(client.get(protests.FILE.format(id=chosen["id"]), timeout=180).text)
    return protests.history(payload), f"{chosen.get('filename')} to {payload['last']}"


def run(out: Path, raw_dir: Path) -> int:
    from geointel.risk.fetch import fetch_all
    from geointel.risk.sources import coups, outlook, ucdp_acd, worldbank

    os.environ["GEOINTEL_SOURCES"] = "ucdp_acd,coups,regimes,vdem,worldbank"
    manifest = fetch_all(raw_dir)
    print("[train] fetched:", {k: v["status"] for k, v in manifest.items()})
    year = datetime.now(UTC).year
    raw = lambda key: raw_dir / manifest[key]["file"]  # noqa: E731
    ucdp_text = ucdp_acd.read_csv_bytes(raw("ucdp_acd").read_bytes())
    internal, _ = ucdp_acd.parse(ucdp_text, start_year=1946)
    coup = coups.parse_any(raw("coups").read_bytes().decode("utf-8", "replace"), year)
    regimes = outlook.owid_regime_series(raw("regimes").read_text())
    edi = trained.owid_numeric_series(raw("vdem").read_text())
    wb = json.loads(raw("worldbank").read_text())
    econ = {
        "growth": worldbank.values(wb.get(worldbank.GDP_GROWTH)),
        "inflation": worldbank.values(wb.get(worldbank.INFLATION)),
    }
    numeric = {c.numeric: c.iso3 for c in universe() if c.numeric}
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for key, indicator in WB.items():
            econ[key] = worldbank.values(client.get(worldbank.url(indicator, year)).json())
        neighbours = trained.topo_neighbours(client.get(TOPO_URL).json(), numeric)
        try:
            protest, protest_note = mass_mobilization(client)
        except Exception as exc:  # noqa: BLE001 - protests are optional (pre-registered)
            protest, protest_note = None, f"{type(exc).__name__}: {exc}"
    print(f"[train] neighbours for {len(neighbours)} countries; protests: {protest_note}")
    countries = {c.iso3: c.first_year for c in universe()}
    last = year - 1
    results = {}
    for key, history, onset, last_year, current in (
        ("coup_attempt", coup, False, min(last, coup.end_year), True),
        ("internal_armed_conflict", internal, True, min(last, internal.end_year), True),
    ) + (
        (("mass_protest", protest, False, protest.end_year, protest.end_year >= last - 1),)
        if protest
        else ()
    ):
        print(f"[train] {key}: validating {trained.FIRST_TEST_YEAR}-{last_year}")
        results[key] = trained.run_type(
            key, history, countries, neighbours, regimes, edi, econ, onset, last_year, current
        )
        r = results[key]
        print(
            f"[train] {key}: events={r.get('test_events')} brier={r.get('brier')} "
            f"bss={r.get('bss_vs_base')} aucpr={r.get('auc_pr')} -> {r.get('decision')}"
        )
    if not protest:
        results["mass_protest"] = {"decision": "no data", "note": protest_note}
    out.parent.mkdir(parents=True, exist_ok=True)
    trained.write(out, trained.report(results))
    return 0
