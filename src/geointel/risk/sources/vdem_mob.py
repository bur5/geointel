"""V-Dem mass mobilisation (``v2cagenmob``) as a stand-in for large protests after 2020.

Mass Mobilization (the protest truth) ends in 2020. V-Dem's expert-coded "frequency and size
of mass mobilisation" runs to the latest year. A country-year counts as a mass-protest year
when the score is at or above a threshold calibrated on the years where both sources exist
(Fable round 4, 3.5; docs/backtest-rules.md, "Protest stand-in"):

* the threshold is chosen on 2000–2015 so that the stand-in flags as many country-years as
  Mass Mobilization does;
* it is checked on 2016–2020; the stand-in is used only if accuracy there is at least 70% and
  Cohen's kappa at least 0.4 (rule written before the first run);
* only the years after Mass Mobilization ends are taken from the stand-in, and they are
  labelled as such.

Source: V-Dem Country-Year dataset (via the ``vdemdata`` R package on GitHub), Coppedge et
al., V-Dem v16 (2026), CC BY-SA 4.0. Extracted by the ``vdem-extract`` workflow into
``cache/vdem_mob.json``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

URL = "https://raw.githubusercontent.com/vdeminstitute/vdemdata/master/data/vdem.RData"
FILE = "vdem_mob.json"
SOURCE = "V-Dem v2cagenmob (mass mobilisation), Coppedge et al., CC BY-SA 4.0"
COLUMNS = ("v2cagenmob", "v2caconmon")
FIRST_YEAR = 1990
TUNE = (2000, 2015)
CHECK = (2016, 2020)
MIN_ACCURACY = 0.70
MIN_KAPPA = 0.40


def extract(rdata_path: str) -> dict:
    """{"columns": [...], "data": {ISO3: {year: [values]}}} from the vdemdata RData file."""
    import pyreadr

    from geointel.risk.countries import universe

    frame = next(iter(pyreadr.read_r(rdata_path).values()))
    codes = {c.iso3 for c in universe()}
    present = [c for c in COLUMNS if c in frame.columns]
    print("[vdem] mobilisation columns:", [c for c in frame.columns if c.startswith("v2ca")][:40])
    if "v2cagenmob" not in present:
        raise RuntimeError("v2cagenmob is missing from the V-Dem file")
    data: dict[str, dict[str, list]] = {}
    version = str(frame["version"].iloc[0]) if "version" in frame.columns else ""
    for row in frame[["country_text_id", "year", *present]].itertuples(index=False):
        iso3, year = str(row[0]), int(row[1])
        if iso3 not in codes or year < FIRST_YEAR:
            continue
        values = [None if v != v else round(float(v), 3) for v in row[2:]]  # NaN → None
        data.setdefault(iso3, {})[str(year)] = values
    return {"columns": present, "version": version, "data": data}


def load(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return payload if payload.get("data") else None


def scores(payload: Mapping, column: str = "v2cagenmob") -> dict[str, dict[int, float]]:
    j = list(payload.get("columns") or COLUMNS).index(column)
    out: dict[str, dict[int, float]] = {}
    for iso3, years in (payload.get("data") or {}).items():
        for year, values in years.items():
            if values and values[j] is not None:
                out.setdefault(iso3, {})[int(year)] = float(values[j])
    return out


def _pairs(score, truth, covered, lo, hi):
    for iso3 in covered:
        for year in range(lo, hi + 1):
            s = score.get(iso3, {}).get(year)
            if s is not None:
                yield s, year in truth.get(iso3, ())


def agreement(pairs: list[tuple[float, bool]], threshold: float) -> dict:
    n = len(pairs)
    tp = sum(1 for s, y in pairs if y and s >= threshold)
    fp = sum(1 for s, y in pairs if not y and s >= threshold)
    fn = sum(1 for s, y in pairs if y and s < threshold)
    tn = n - tp - fp - fn
    acc = (tp + tn) / n if n else 0.0
    p_yes = ((tp + fp) / n) * ((tp + fn) / n) if n else 0.0
    p_no = ((tn + fn) / n) * ((tn + fp) / n) if n else 0.0
    expected = p_yes + p_no
    kappa = (acc - expected) / (1 - expected) if expected < 1 else 0.0
    return {
        "n": n,
        "accuracy": round(acc, 3),
        "kappa": round(kappa, 3),
        "recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "rate_truth": round((tp + fn) / n, 3) if n else None,
        "rate_proxy": round((tp + fp) / n, 3) if n else None,
    }


def calibrate(
    score: Mapping[str, Mapping[int, float]],
    truth: Mapping[str, Iterable],
    covered: Iterable[str],
) -> dict:
    """Threshold matching the Mass Mobilization rate on the tuning years, checked after."""
    covered = list(covered)
    truth = {k: set(v) for k, v in truth.items()}
    tune = list(_pairs(score, truth, covered, *TUNE))
    check = list(_pairs(score, truth, covered, *CHECK))
    if not tune or not check:
        return {"usable": False, "reason": "no overlap"}
    events = sum(1 for _, y in tune if y)
    ordered = sorted((s for s, _ in tune), reverse=True)
    threshold = ordered[max(events - 1, 0)]
    check_stats = agreement(check, threshold)
    usable = check_stats["accuracy"] >= MIN_ACCURACY and check_stats["kappa"] >= MIN_KAPPA
    return {
        "usable": usable,
        "threshold": round(threshold, 3),
        "tuning": agreement(tune, threshold),
        "check": check_stats,
        "rule": f"accuracy ≥ {MIN_ACCURACY:.0%} and kappa ≥ {MIN_KAPPA} on {CHECK[0]}–{CHECK[1]}",
    }


def extend(protests: Mapping, score: Mapping[str, Mapping[int, float]], threshold: float) -> dict:
    """Mass Mobilization payload extended past its last year with stand-in years."""
    last = int(protests["last"])
    proxy_last = max((y for years in score.values() for y in years), default=last)
    years = {k: set(v) for k, v in protests["years"].items()}
    for iso3 in protests["covered"]:
        for year, s in (score.get(iso3) or {}).items():
            if last < year <= proxy_last and s >= threshold:
                years.setdefault(iso3, set()).add(year)
    return {
        **protests,
        "last": proxy_last,
        "years": {k: sorted(v) for k, v in years.items()},
        "proxy_from": last + 1,
    }


def main(argv: list[str] | None = None) -> int:
    import sys

    rdata, out = argv if argv is not None else sys.argv[1:]
    payload = extract(rdata)
    Path(out).write_text(json.dumps(payload, separators=(",", ":")))
    last = max(int(y) for years in payload["data"].values() for y in years)
    print(f"[vdem] {len(payload['data'])} countries, last year {last}, {payload['version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
