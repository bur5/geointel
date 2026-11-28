"""Trained base models (country-year logistic regression) with pre-registered forward
validation — see docs/validation-rules.md.

Run in its own workflow (``python -m geointel.risk train --out models.json``); the daily
pipeline only reads the resulting file. A type is switched on only if it passes the rule
written before the first run: the lower end of the 95% bootstrap interval of the Brier skill
score against the current base-rate model is above zero, with at least 30 test events.
"""

import json
import math
import random
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime

from geointel.risk.model import TypeHistory, assess_type

FIRST_YEAR = 1995
FIRST_TEST_YEAR = 2005
L2 = 1.0
BOOTSTRAP = 1000
MIN_EVENTS = 30

FEATURES = (
    "log_years_since",
    "events_5y",
    "neighbour_share",
    "regime_0",
    "regime_1",
    "regime_2",
    "regime_change_3y",
    "edi",
    "log_gdppc",
    "growth",
    "log_inflation",
    "infant_mortality",
    "log_population",
    "econ_missing",
)


# ---------------------------------------------------------------------------------- data
def owid_numeric_series(text: str) -> dict[str, dict[int, float]]:
    import csv
    import io

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    header = [h.strip().lower() for h in rows[0]]
    code_i, year_i = header.index("code"), header.index("year")
    # The value is the first column after the year (later columns can be confidence bounds
    # or a region label).
    value_i = year_i + 1
    out: dict[str, dict[int, float]] = defaultdict(dict)
    for row in rows[1:]:
        try:
            out[row[code_i].upper()][int(row[year_i])] = float(row[value_i])
        except (IndexError, ValueError):
            continue
    return dict(out)


def topo_neighbours(topology: Mapping, numeric_to_iso3: Mapping[str, str]) -> dict[str, set]:
    """Countries sharing an arc in a TopoJSON world map are land neighbours."""
    by_arc: dict[int, set[str]] = defaultdict(set)

    def arcs_of(geometry) -> list[int]:
        out: list[int] = []

        def walk(x):
            if isinstance(x, int):
                out.append(x if x >= 0 else ~x)
            elif isinstance(x, list):
                for y in x:
                    walk(y)

        walk(geometry.get("arcs") or [])
        return out

    objects = topology.get("objects") or {}
    countries = objects.get("countries") or next(iter(objects.values()), {})
    for geometry in countries.get("geometries") or []:
        iso3 = numeric_to_iso3.get(str(geometry.get("id", "")).zfill(3))
        if not iso3:
            continue
        for arc in arcs_of(geometry):
            by_arc[arc].add(iso3)
    neighbours: dict[str, set] = defaultdict(set)
    for members in by_arc.values():
        for a in members:
            neighbours[a] |= members - {a}
    return dict(neighbours)


# ---------------------------------------------------------------------------------- panel
def _since(years: frozenset, year: int) -> int:
    before = [y for y in years if y < year]
    return min(year - max(before), 50) if before else 50


def features(
    iso3: str,
    year: int,
    events: Mapping[str, frozenset],
    neighbours: Mapping[str, set],
    regimes: Mapping[str, Mapping[int, int]],
    edi: Mapping[str, Mapping[int, float]],
    econ: Mapping[str, Mapping[tuple[str, int], float]],
) -> dict[str, float | None]:
    """Feature row for predicting ``year`` — only values from ``year - 1`` and earlier."""
    prev = year - 1
    own = events.get(iso3, frozenset())
    nbs = neighbours.get(iso3, set())
    share = sum(1 for n in nbs if prev in events.get(n, frozenset())) / len(nbs) if nbs else 0.0
    reg = regimes.get(iso3, {})
    r_now, r_then = reg.get(prev), reg.get(year - 4)
    row: dict[str, float | None] = {
        "log_years_since": math.log1p(_since(own, year)),
        "events_5y": float(sum(1 for y in own if prev - 4 <= y <= prev)),
        "neighbour_share": share,
        "regime_0": None if r_now is None else float(r_now == 0),
        "regime_1": None if r_now is None else float(r_now == 1),
        "regime_2": None if r_now is None else float(r_now == 2),
        "regime_change_3y": None if r_now is None or r_then is None else float(r_now != r_then),
        "edi": edi.get(iso3, {}).get(prev),
    }
    gdppc = econ.get("gdppc", {}).get((iso3, prev))
    growth = econ.get("growth", {}).get((iso3, prev))
    infl = econ.get("inflation", {}).get((iso3, prev))
    imr = econ.get("imr", {}).get((iso3, prev))
    pop = econ.get("pop", {}).get((iso3, prev))
    row.update(
        log_gdppc=math.log(gdppc) if gdppc and gdppc > 0 else None,
        growth=None if growth is None else max(min(growth, 30.0), -30.0),
        log_inflation=None if infl is None else math.copysign(math.log1p(abs(infl)), infl),
        infant_mortality=imr,
        log_population=math.log(pop) if pop and pop > 0 else None,
        econ_missing=float(gdppc is None or growth is None),
    )
    return row


def fill_missing(rows: list[dict], reference: list[dict] | None = None) -> list[list[float]]:
    """Median imputation per feature. Medians come from ``reference`` (the training rows)
    when given, so test rows never inform their own filling (Fable round 4, #10)."""
    medians = {}
    for f in FEATURES:
        vals = sorted(
            r[f] for r in (reference if reference is not None else rows) if r[f] is not None
        )
        medians[f] = vals[len(vals) // 2] if vals else 0.0
    return [[1.0] + [r[f] if r[f] is not None else medians[f] for f in FEATURES] for r in rows]


# ---------------------------------------------------------------------------------- model
def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        if abs(m[col][col]) < 1e-12:
            continue
        for r in range(n):
            if r != col:
                factor = m[r][col] / m[col][col]
                for c in range(col, n + 1):
                    m[r][c] -= factor * m[col][c]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def standardise(x: list[list[float]]) -> tuple[list[float], list[float]]:
    k = len(x[0])
    means, sds = [0.0] * k, [1.0] * k
    for j in range(1, k):
        col = [row[j] for row in x]
        mu = sum(col) / len(col)
        sd = math.sqrt(sum((v - mu) ** 2 for v in col) / max(len(col) - 1, 1)) or 1.0
        means[j], sds[j] = mu, sd
    return means, sds


def fit_logistic(x: list[list[float]], y: list[int], l2: float = L2, iters: int = 30) -> dict:
    means, sds = standardise(x)
    z = [[(v - means[j]) / sds[j] if j else 1.0 for j, v in enumerate(row)] for row in x]
    k = len(z[0])
    beta = [0.0] * k
    rate = max(sum(y) / len(y), 1e-4)
    beta[0] = math.log(rate / (1 - rate))

    def penalised_loglik(b: list[float]) -> float:
        total = 0.0
        for row, target in zip(z, y, strict=True):
            eta = max(min(sum(bi * v for bi, v in zip(b, row, strict=True)), 30), -30)
            total += target * eta - math.log1p(math.exp(eta))
        return total - 0.5 * l2 * sum(bi * bi for bi in b[1:])

    current = penalised_loglik(beta)
    hess = [[0.0] * k for _ in range(k)]
    for _ in range(iters):
        grad = [0.0] * k
        hess = [[0.0] * k for _ in range(k)]
        for row, target in zip(z, y, strict=True):
            eta = sum(b * v for b, v in zip(beta, row, strict=True))
            p = 1 / (1 + math.exp(-max(min(eta, 30), -30)))
            w = p * (1 - p)
            for i in range(k):
                grad[i] += (target - p) * row[i]
                wi = w * row[i]
                for j in range(i, k):
                    hess[i][j] += wi * row[j]
        for i in range(k):
            for j in range(i):
                hess[i][j] = hess[j][i]
            if i:
                grad[i] -= l2 * beta[i]
                hess[i][i] += l2
        step = _solve(hess, grad)
        biggest = max(abs(s_) for s_ in step) or 1.0
        if biggest > 5:  # damped Newton: never jump far in one iteration
            step = [s_ * 5 / biggest for s_ in step]
        scale = 1.0
        for _half in range(30):
            trial = [b + scale * s_ for b, s_ in zip(beta, step, strict=True)]
            value = penalised_loglik(trial)
            if value >= current - 1e-9:
                break
            scale /= 2
        else:
            break
        beta, gain, current = trial, value - current, value
        if max(abs(scale * s_) for s_ in step) < 1e-6 or gain < 1e-8:
            break
    cov = _inverse(hess)  # covariance = inverse Hessian, not 1/diagonal (Fable round 4, #9)
    return {"beta": beta, "means": means, "sds": sds, "cov": cov}


def _inverse(a: list[list[float]]) -> list[list[float]]:
    n = len(a)
    cols = [_solve(a, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def link_se(model: Mapping, row: list[float]) -> float:
    """Standard error of the linear predictor: sqrt(zᵀ Σ z) with the full covariance."""
    z = [((v - model["means"][j]) / model["sds"][j]) if j else 1.0 for j, v in enumerate(row)]
    cov = model["cov"]
    total = sum(z[i] * cov[i][j] * z[j] for i in range(len(z)) for j in range(len(z)))
    return math.sqrt(max(total, 0.0))


def fit_offset_logistic(
    x: list[list[float]], y: list[int], offset: list[float], l2: float = 20.0, iters: int = 40
) -> dict:
    """Logistic regression around a given forecast: logit p = offset + β·z, every coefficient
    (intercept included) shrunk to zero. With uninformative features the model returns the
    offset forecast itself (Fable round 4, 3.4)."""
    means, sds = standardise(x)
    z = [[(v - means[j]) / sds[j] if j else 1.0 for j, v in enumerate(row)] for row in x]
    k = len(z[0])
    beta = [0.0] * k
    for _ in range(iters):
        grad = [-l2 * b for b in beta]
        hess = [[l2 if i == j else 0.0 for j in range(k)] for i in range(k)]
        for row, target, off in zip(z, y, offset, strict=True):
            eta = off + sum(b * v for b, v in zip(beta, row, strict=True))
            p = 1 / (1 + math.exp(-max(min(eta, 30), -30)))
            w = p * (1 - p)
            for i in range(k):
                grad[i] += (target - p) * row[i]
                for j in range(i, k):
                    hess[i][j] += w * row[i] * row[j]
        for i in range(k):
            for j in range(i):
                hess[i][j] = hess[j][i]
        step = _solve(hess, grad)
        beta = [b + s_ for b, s_ in zip(beta, step, strict=True)]
        if max(abs(s_) for s_ in step) < 1e-7:
            break
    return {"beta": beta, "means": means, "sds": sds}


def predict_offset(model: Mapping, row: list[float], offset: float) -> float:
    eta = offset + sum(
        b * ((v - model["means"][j]) / model["sds"][j] if j else 1.0)
        for j, (b, v) in enumerate(zip(model["beta"], row, strict=True))
    )
    return 1 / (1 + math.exp(-max(min(eta, 30), -30)))


def _expit(x: float) -> float:
    return 1 / (1 + math.exp(-max(min(x, 30.0), -30.0)))


def predict(model: Mapping, row: list[float]) -> float:
    eta = sum(
        b * ((v - model["means"][j]) / model["sds"][j] if j else 1.0)
        for j, (b, v) in enumerate(zip(model["beta"], row, strict=True))
    )
    return 1 / (1 + math.exp(-max(min(eta, 30), -30)))


# ---------------------------------------------------------------------------------- metrics
def brier(ps: list[float], ys: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys, strict=True)) / len(ys)


def log_score(ps: list[float], ys: list[int]) -> float:
    return -sum(
        math.log(min(max(p if y else 1 - p, 1e-6), 1)) for p, y in zip(ps, ys, strict=True)
    ) / len(ys)


def auc_pr(ps: list[float], ys: list[int]) -> float | None:
    positives = sum(ys)
    if not positives:
        return None
    hits, total = 0, 0.0
    for rank, (_, y) in enumerate(sorted(zip(ps, ys, strict=True), key=lambda t: -t[0]), 1):
        if y:
            hits += 1
            total += hits / rank
    return total / positives


def calibration(ps: list[float], ys: list[int], bins: int = 5) -> list[dict]:
    pairs = sorted(zip(ps, ys, strict=True))
    size = max(len(pairs) // bins, 1)
    out = []
    for b in range(bins):
        chunk = pairs[b * size : (b + 1) * size if b < bins - 1 else len(pairs)]
        if chunk:
            out.append(
                {
                    "predicted": round(sum(p for p, _ in chunk) / len(chunk), 4),
                    "observed": round(sum(y for _, y in chunk) / len(chunk), 4),
                    "n": len(chunk),
                }
            )
    return out


def bootstrap_bss(records: list[tuple[str, float, float, int]], seed: int = 11) -> tuple:
    """95% interval of the Brier skill score (model vs baseline), resampling whole countries."""
    rng = random.Random(seed)
    by_country: dict[str, list] = defaultdict(list)
    for iso3, p, base, y in records:
        by_country[iso3].append((p, base, y))
    keys = list(by_country)
    scores = []
    for _ in range(BOOTSTRAP):
        sample = [r for k in (rng.choice(keys) for _ in keys) for r in by_country[k]]
        bm = sum((p - y) ** 2 for p, _, y in sample)
        bb = sum((b - y) ** 2 for _, b, y in sample)
        scores.append(1 - bm / bb if bb else 0.0)
    scores.sort()
    return scores[int(0.025 * BOOTSTRAP)], scores[int(0.975 * BOOTSTRAP) - 1]


# ---------------------------------------------------------------------------------- run
def _truncate(history: TypeHistory, end_year: int) -> TypeHistory:
    from dataclasses import replace

    return replace(
        history,
        end_year=end_year,
        years_with_event={
            k: frozenset(y for y in v if y <= end_year) for k, v in history.years_with_event.items()
        },
    )


def run_type(
    key: str,
    history: TypeHistory,
    countries: Mapping[str, int | None],
    neighbours: Mapping[str, set],
    regimes: Mapping[str, Mapping[int, int]],
    edi: Mapping[str, Mapping[int, float]],
    econ: Mapping[str, Mapping[tuple[str, int], float]],
    onset_only: bool,
    last_year: int,
    current_ok: bool = True,
) -> dict:
    events = history.years_with_event

    def at_risk(iso3: str, year: int) -> bool:
        return not (onset_only and (year - 1) in events.get(iso3, frozenset()))

    def target(iso3: str, year: int) -> int:
        return int(year in events.get(iso3, frozenset()))

    cache: dict[int, list] = {}

    def year_rows(year: int) -> list[tuple[str, int, dict, int]]:
        if year not in cache:
            cache[year] = [
                (
                    iso3,
                    year,
                    features(iso3, year, events, neighbours, regimes, edi, econ),
                    target(iso3, year),
                )
                for iso3, first in countries.items()
                if not (first and year < first) and at_risk(iso3, year)
            ]
        return cache[year]

    def rows_for(years: range) -> list[tuple[str, int, dict, int]]:
        return [row for year in years for row in year_rows(year)]

    records, persistence_records = [], []
    for test_year in range(FIRST_TEST_YEAR, last_year + 1):
        train = rows_for(range(FIRST_YEAR, test_year))
        test = rows_for(range(test_year, test_year + 1))
        if not test or sum(y for *_, y in train) < 10:
            continue
        x_all = fill_missing(
            [f for _, _, f, _ in train] + [f for _, _, f, _ in test],
            reference=[f for _, _, f, _ in train],
        )
        x_train, x_test = x_all[: len(train)], x_all[len(train) :]
        model = fit_logistic(x_train, [y for *_, y in train])
        truncated = _truncate(history, test_year - 1)
        groups = None
        if key == "coup_attempt" and regimes:
            groups = {}
            for c in countries:
                known = [y for y in (regimes.get(c) or {}) if y <= test_year - 1]
                if not known:  # never a regime from the future (Fable round 4, #11)
                    continue
                n20 = sum(1 for y in events.get(c, ()) if test_year - 20 <= y <= test_year - 1)
                groups[c] = f"{regimes[c][max(known)]}|{'coup20' if n20 >= 2 else 'none20'}"
        base = {
            r.iso3: r.horizons["1y"].p
            for r in assess_type(truncated, countries, onset_only, groups)
        }
        prev_rate = defaultdict(lambda: [0, 0])
        for iso3, year, _, y in train:
            k = int((year - 1) in events.get(iso3, frozenset()))
            prev_rate[k][0] += y
            prev_rate[k][1] += 1
        for (iso3, year, _, y), row in zip(test, x_test, strict=True):
            if iso3 not in base:
                continue
            k = int((year - 1) in events.get(iso3, frozenset()))
            persist = prev_rate[k][0] / prev_rate[k][1] if prev_rate[k][1] else 0.0
            records.append((iso3, predict(model, row), base[iso3], y))
            persistence_records.append(persist)
    ps = [p for _, p, _, _ in records]
    bs = [b for _, _, b, _ in records]
    ys = [y for *_, y in records]
    events_n = sum(ys)
    result: dict = {
        "test_years": [FIRST_TEST_YEAR, last_year],
        "test_rows": len(ys),
        "test_events": events_n,
    }
    if not records:
        result["decision"] = "no data"
        return result
    b_model, b_base = brier(ps, ys), brier(bs, ys)
    b_persist = brier(persistence_records, ys)
    low, high = bootstrap_bss(records)
    passed = events_n >= MIN_EVENTS and low > 0 and current_ok
    result.update(
        brier={
            "model": round(b_model, 5),
            "base_rate": round(b_base, 5),
            "persistence": round(b_persist, 5),
        },
        bss_vs_base={
            "value": round(1 - b_model / b_base, 4),
            "ci95": [round(low, 4), round(high, 4)],
        },
        log_score={"model": round(log_score(ps, ys), 4), "base_rate": round(log_score(bs, ys), 4)},
        auc_pr={"model": auc_pr(ps, ys), "base_rate": auc_pr(bs, ys)},
        calibration={"model": calibration(ps, ys), "base_rate": calibration(bs, ys)},
        enough_for_calibration=events_n >= 50,
        decision="switch on"
        if passed
        else (
            "not enough data"
            if events_n < MIN_EVENTS
            else "no current data"
            if not current_ok
            else "keep base rate"
        ),
    )
    # Final model on all years, predictions for next year.
    train = rows_for(range(FIRST_YEAR, last_year + 1))
    nxt = [
        (c, last_year + 1, features(c, last_year + 1, events, neighbours, regimes, edi, econ))
        for c in countries
        if at_risk(c, last_year + 1)
    ]
    x_all = fill_missing(
        [f for _, _, f, _ in train] + [f for *_, f in nxt],
        reference=[f for _, _, f, _ in train],
    )
    model = fit_logistic(x_all[: len(train)], [y for *_, y in train])
    preds = {}
    for (iso3, _, _), row in zip(nxt, x_all[len(train) :], strict=True):
        p = predict(model, row)
        p = min(max(p, 1e-9), 1 - 1e-9)
        eta = math.log(p / (1 - p))
        se = link_se(model, row)
        preds[iso3] = {
            "p": round(p, 5),
            "low": round(_expit(eta - 1.645 * se), 5),
            "high": round(_expit(eta + 1.645 * se), 5),
        }
    result["coefficients"] = dict(
        zip(("intercept", *FEATURES), (round(b, 4) for b in model["beta"]), strict=True)
    )
    result["predictions"] = preds
    result["predicted_year"] = last_year + 1
    return result


def report(results: Mapping[str, dict]) -> dict:
    return {
        "schema": "geointel-trained-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "rules": "docs/validation-rules.md",
        "types": dict(results),
    }


def write(path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def apply_trained(snapshot: dict, report_data: Mapping | None) -> list[str]:
    """Replace base-rate horizons by trained predictions for types that passed validation
    (onset questions of countries not in an active state). Returns the switched types."""
    from geointel.risk.model import onset_within
    from geointel.risk.taxonomy import HORIZONS

    switched = []
    for key, result in ((report_data or {}).get("types") or {}).items():
        if result.get("decision") != "switch on":
            continue
        preds = result.get("predictions") or {}
        for country in snapshot.get("countries", []):
            risk = (country.get("risks") or {}).get(key)
            pred = preds.get(country["iso3"])
            if not risk or not pred or risk.get("question") != "onset_within":
                continue
            risk["horizons"] = {
                h.key: {
                    "p": round(onset_within(pred["p"], h.years), 4),
                    "low": round(onset_within(pred["low"], h.years), 4),
                    "high": round(onset_within(pred["high"], h.years), 4),
                }
                for h in HORIZONS
            }
            risk["model"] = "trained"
        for entry in snapshot.get("event_types", []):
            if entry["key"] == key:
                entry["trained"] = {
                    "bss": result.get("bss_vs_base"),
                    "test_events": result.get("test_events"),
                    "generated_at": (report_data or {}).get("generated_at"),
                }
        switched.append(key)
    return switched
