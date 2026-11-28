"""Time machine for the base model (docs/backtest-rules.md).

For every issue year Y the model sees each history only up to the last year whose data were
published by 1 January Y (the ``as_of`` rule), forecasts the event in calendar year Y, and the
forecast is scored against what happened. Model code receives truncated histories only; the
full history is used for outcomes and nothing else.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping
from dataclasses import replace
from statistics import fmean

from geointel.risk.model import (
    GROUP_PRIOR_CAP_MULT,
    MIN_GROUP_COUNTRIES,
    Counts,
    TypeHistory,
    bernoulli_counts,
    exposure,
    fit_prior,
    posterior,
    transition_counts,
)
from geointel.risk.taxonomy import EventType

# Years between the data year and 1 January of the issue year (publication lag, rules table).
LAG = {
    EventType.INTERNAL_ARMED_CONFLICT: 2,
    EventType.INTERSTATE_CONFLICT: 2,
    EventType.COUP_ATTEMPT: 2,
    EventType.MASS_PROTEST: 2,
    EventType.ECONOMIC_CRISIS: 2,
    EventType.HUMANITARIAN_CRISIS: 1,
    EventType.MAJOR_EARTHQUAKE: 1,
    EventType.TSUNAMI: 1,
}
REGIME_LAG = 2
PERIODS = {"tuning": (2000, 2015), "validation": (2016, 2020), "holdout": (2021, 2025)}
CLASS_A = (EventType.INTERNAL_ARMED_CONFLICT, EventType.INTERSTATE_CONFLICT)
EPS = 1e-6


def as_of(history: TypeHistory, last_year: int) -> TypeHistory:
    """The history as it could be known when data up to ``last_year`` were published."""
    events = {
        iso3: frozenset(y for y in years if y <= last_year)
        for iso3, years in history.years_with_event.items()
    }
    observed = None
    if history.observed_years is not None:
        observed = {
            iso3: frozenset(y for y in years if y <= last_year)
            for iso3, years in history.observed_years.items()
        }
    return replace(
        history,
        end_year=min(history.end_year, last_year),
        years_with_event=events,
        observed_years=observed,
    )


def regimes_as_of(series: Mapping[str, Mapping[int, int]], last_year: int) -> dict[str, int]:
    out = {}
    for iso3, by_year in series.items():
        known = [y for y in by_year if y <= last_year]
        if known:
            out[iso3] = by_year[max(known)]
    return out


def coup_groups_as_of(history: TypeHistory, regimes: Mapping[str, int]) -> dict[str, str]:
    """Same grouping as the live model (snapshot.coup_groups) on as-of data."""
    recent_from = history.end_year - 19
    return {
        iso3: f"{regime}|"
        + (
            "coup20"
            if sum(1 for y in history.years_with_event.get(iso3, ()) if y >= recent_from) >= 2
            else "none20"
        )
        for iso3, regime in regimes.items()
    }


def _two_step(active: bool, p01: float, p11: float, steps: int) -> float:
    p = 1.0 if active else 0.0
    for _ in range(steps):
        p = p * p11 + (1 - p) * p01
    return p


def forecasts(
    history: TypeHistory,
    first_years: Mapping[str, int | None],
    persistent: bool,
    issue_year: int,
    lag: int,
    groups: Mapping[str, str] | None = None,
    cap_mult: float | None = None,
    world_cap_mult: float | None = None,
    gap: int | None = None,
) -> dict[str, dict]:
    """P(event in ``issue_year``) per country from data up to ``issue_year - lag``.

    Mirrors model.assess_type (posterior means) and adds the steps between the last known
    year and the target year for persistent types."""
    known = as_of(history, issue_year - lag)
    steps = issue_year - known.end_year
    countries = {
        iso3: first for iso3, first in first_years.items() if (first or 0) <= known.end_year
    }
    out: dict[str, dict] = {}
    if persistent:
        trans = {iso3: transition_counts(known, iso3, f, gap) for iso3, f in countries.items()}
        prior01 = fit_prior(t[0] for t in trans.values())
        prior11 = fit_prior(t[1] for t in trans.values() if t[1].trials > 0)
        for iso3, first in countries.items():
            span = exposure(known, first, iso3)
            if not span:
                continue
            active = span[-1] in known.years_with_event.get(iso3, ())
            p01 = posterior(prior01, trans[iso3][0]).mean
            p11 = posterior(prior11, trans[iso3][1]).mean
            out[iso3] = {
                "p": _two_step(active, p01, p11, steps),
                "state": "continuation" if active else "onset",
            }
        return out
    simple = {iso3: bernoulli_counts(known, iso3, f) for iso3, f in countries.items()}
    if world_cap_mult is not None:
        usable = [c for c in simple.values() if c.trials >= 1.0]
        world = fit_prior(
            usable, max_strength=max(2.0, world_cap_mult * fmean(c.trials for c in usable))
        )
    else:
        world = fit_prior(simple.values())
    group_prior = {}
    if groups:
        members: dict[str, list[Counts]] = {}
        for iso3, c in simple.items():
            if iso3 in groups and c.trials >= 1.0:
                members.setdefault(groups[iso3], []).append(c)
        for g, cs in members.items():
            if len(cs) >= MIN_GROUP_COUNTRIES:
                mult = GROUP_PRIOR_CAP_MULT if cap_mult is None else cap_mult
                cap = 400.0 if mult >= 1e8 else max(2.0, mult * fmean(c.trials for c in cs))
                group_prior[g] = fit_prior(cs, world, max_strength=cap)
    for iso3, first in countries.items():
        if not exposure(known, first, iso3):
            continue
        prior = group_prior.get((groups or {}).get(iso3, ""), world)
        out[iso3] = {"p": posterior(prior, simple[iso3]).mean, "state": "all"}
    return out


def references(
    history: TypeHistory,
    first_years: Mapping[str, int | None],
    issue_year: int,
    lag: int,
) -> dict[str, dict[str, float]]:
    """Reference forecasts from the same as-of data: the world frequency and
    'same as the last known year' (frequency of the event given the last known state)."""
    known = as_of(history, issue_year - lag)
    steps = issue_year - known.end_year
    hits = total = 0
    after = {True: [0, 0], False: [0, 0]}
    last_state = {}
    for iso3, first in first_years.items():
        if (first or 0) > known.end_year:
            continue
        span = exposure(known, first, iso3)
        events = known.years_with_event.get(iso3, frozenset())
        for year in span:
            hits += year in events
            total += 1
            if year - steps in span:
                prev = (year - steps) in events
                after[prev][0] += year in events
                after[prev][1] += 1
        if span:
            last_state[iso3] = span[-1] in events
    world = hits / total if total else 0.0
    cond = {k: (v[0] + world) / (v[1] + 1) for k, v in after.items()}
    return {iso3: {"world": world, "last_year": cond[state]} for iso3, state in last_state.items()}


def outcome(history: TypeHistory, iso3: str, year: int) -> int | None:
    if history.observed_years is not None and year not in history.observed_years.get(iso3, ()):
        return None
    if year > history.end_year:
        return None
    return int(year in history.years_with_event.get(iso3, frozenset()))


def brier(rows: list[tuple[float, int]]) -> float:
    return fmean((p - y) ** 2 for p, y in rows) if rows else float("nan")


def log_score(rows: list[tuple[float, int]]) -> float:
    return (
        fmean(-math.log(min(max(p if y else 1 - p, EPS), 1.0)) for p, y in rows)
        if rows
        else float("nan")
    )


def auc_pr(rows: list[tuple[float, int]]) -> float | None:
    positives = sum(y for _, y in rows)
    if not positives:
        return None
    ranked = sorted(rows, key=lambda r: -r[0])
    tp = fp = 0
    area = 0.0
    prev_recall = 0.0
    for _p, y in ranked:
        tp += y
        fp += 1 - y
        recall = tp / positives
        precision = tp / (tp + fp)
        area += (recall - prev_recall) * precision
        prev_recall = recall
    return area


def calibration(rows: list[tuple[float, int]], bins: int = 10) -> list[dict]:
    ranked = sorted(rows)
    if not ranked:
        return []
    size = max(1, math.ceil(len(ranked) / bins))
    out = []
    for i in range(0, len(ranked), size):
        chunk = ranked[i : i + size]
        out.append(
            {
                "forecast": round(fmean(p for p, _ in chunk), 4),
                "observed": round(fmean(y for _, y in chunk), 4),
                "n": len(chunk),
            }
        )
    return out


def skill_interval(
    records: list[dict], ref: str, samples: int = 1000, seed: int = 7
) -> tuple[float, float, float] | None:
    """Brier skill score against a reference with a 95% bootstrap interval over countries
    (whole countries are resampled, so the years of one country stay together)."""
    by_country: dict[str, list[dict]] = {}
    for r in records:
        by_country.setdefault(r["iso3"], []).append(r)
    codes = sorted(by_country)
    if not codes:
        return None

    def bss(rows: Iterable[dict]) -> float | None:
        rows = list(rows)
        model = brier([(r["p"], r["y"]) for r in rows])
        base = brier([(r[ref], r["y"]) for r in rows])
        return None if not base else 1 - model / base

    point = bss(records)
    if point is None:
        return None
    rng = random.Random(seed)
    draws = []
    for _ in range(samples):
        pick = [r for c in (rng.choice(codes) for _ in codes) for r in by_country[c]]
        value = bss(pick)
        if value is not None:
            draws.append(value)
    draws.sort()
    lo = draws[int(0.025 * len(draws))]
    hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
    return round(point, 4), round(lo, 4), round(hi, 4)


def coup_features(known: TypeHistory, iso3: str, regime: int | None) -> list[float]:
    """Features for the coup offset model, from as-of data only."""
    years = known.years_with_event.get(iso3, frozenset())
    since = min(known.end_year - max(years), 50) if years else 50
    recent = sum(1 for y in years if y > known.end_year - 10)
    return [
        1.0,
        math.log1p(since),
        float(recent),
        float(regime == 0) if regime is not None else 0.0,
        float(regime == 1) if regime is not None else 0.0,
        float(regime is not None and regime >= 2),
    ]


def run_type(
    key: EventType,
    history: TypeHistory,
    first_years: Mapping[str, int | None],
    persistent: bool,
    years: Iterable[int],
    regime_series: Mapping[str, Mapping[int, int]] | None = None,
    variant: Mapping | None = None,
) -> list[dict]:
    """``variant`` (coups only): {"groups": "all" | "democracies" | None,
    "cap": group prior cap multiplier, "world_cap": world prior cap multiplier}."""
    if variant is None:
        variant = LIVE_COUP_VARIANT if key == EventType.COUP_ATTEMPT else {}
    lag = LAG.get(key, 2)
    records = []
    for year in years:
        groups = None
        regimes: dict[str, int] = {}
        known = as_of(history, year - lag)
        if key == EventType.COUP_ATTEMPT and regime_series:
            regimes = regimes_as_of(regime_series, year - REGIME_LAG)
            if variant.get("groups"):
                groups = coup_groups_as_of(known, regimes)
                if variant["groups"] == "democracies":
                    groups = {c: g for c, g in groups.items() if g in ("3|none20", "2|none20")}
        fc = forecasts(
            history,
            first_years,
            persistent,
            year,
            lag,
            groups,
            variant.get("cap"),
            variant.get("world_cap"),
            variant.get("gap"),
        )
        refs = references(history, first_years, year, lag)
        for iso3, item in fc.items():
            y = outcome(history, iso3, year)
            if y is None or iso3 not in refs:
                continue
            record = {
                "iso3": iso3,
                "year": year,
                "state": item["state"],
                "p": item["p"],
                "y": y,
                **refs[iso3],
            }
            if key == EventType.COUP_ATTEMPT:
                record["x"] = coup_features(known, iso3, regimes.get(iso3))
            records.append(record)
    return records


def offset_records(
    records: list[dict], lag: int, first_fit_year: int, l2: float = 20.0
) -> list[dict]:
    """Coup offset model on top of a base variant's records: for each year Y, fit on the
    records whose outcome was known by then (year <= Y - lag) and correct Y's base forecast."""
    from geointel.risk.trained import fit_offset_logistic, predict_offset

    by_year: dict[int, list[dict]] = {}
    for r in records:
        by_year.setdefault(r["year"], []).append(r)

    def logit(p: float) -> float:
        p = min(max(p, EPS), 1 - EPS)
        return math.log(p / (1 - p))

    out = []
    for year in sorted(by_year):
        if year < first_fit_year:
            continue
        train = [r for y, rs in by_year.items() if y <= year - lag for r in rs]
        if sum(r["y"] for r in train) < 20:
            continue
        model = fit_offset_logistic(
            [r["x"] for r in train],
            [r["y"] for r in train],
            [logit(r["p"]) for r in train],
            l2=l2,
        )
        for r in by_year[year]:
            out.append({**r, "p": predict_offset(model, r["x"], logit(r["p"]))})
    return out


def summarise(records: list[dict]) -> dict:
    rows = [(r["p"], r["y"]) for r in records]
    result = {
        "n": len(rows),
        "events": sum(y for _, y in rows),
        "brier": round(brier(rows), 5),
        "log_score": round(log_score(rows), 4),
        "auc_pr": None if auc_pr(rows) is None else round(auc_pr(rows), 4),
        "calibration": calibration(rows),
    }
    for ref in ("world", "last_year"):
        interval = skill_interval(records, ref)
        result[f"bss_vs_{ref}"] = None if interval is None else list(interval)
    return result


def danger_check(records_by_type: Mapping[EventType, list[dict]]) -> dict:
    """Order and band checks of the class-A danger level (no ministries, no news).

    For each country-year the level is 4 if a class-A conflict was active in the last known
    year, else the class-A level from the onset probability (thresholds 2/5/20%, capped at 3
    as in the live model); the outcome is any class-A conflict in the target year."""
    from geointel.risk.danger import ONSET_CAP, THRESHOLDS

    lows = THRESHOLDS["A"]
    cells: dict[tuple[str, int], dict] = {}
    for key in CLASS_A:
        for r in records_by_type.get(key, []):
            cell = cells.setdefault((r["iso3"], r["year"]), {"level": 1, "y": 0, "from_p": False})
            if r["state"] == "continuation":
                cell["level"] = max(cell["level"], 4)
            else:
                level = min(1 + sum(1 for x in lows if r["p"] >= x), ONSET_CAP)
                if level > cell["level"]:
                    cell["level"], cell["from_p"] = level, True
            cell["y"] = max(cell["y"], r["y"])
    by_level: dict[int, list[int]] = {}
    for cell in cells.values():
        by_level.setdefault(cell["level"], []).append(cell["y"])
    rates = {
        lvl: {"n": len(ys), "rate": round(fmean(ys), 4)} for lvl, ys in sorted(by_level.items())
    }
    ordered = [rates[k]["rate"] for k in sorted(rates)]
    band_rows = [c["y"] for c in cells.values() if c["level"] == 3 and c["from_p"]]
    band = None
    if band_rows:
        n = len(band_rows)
        rate = fmean(band_rows)
        half = 1.96 * math.sqrt(max(rate * (1 - rate), 1e-9) / n)
        band = {
            "n": n,
            "rate": round(rate, 4),
            "low": round(max(0.0, rate - half), 4),
            "high": round(min(1.0, rate + half), 4),
            "promised": [lows[1], lows[2]],
            "inside": (rate + half) >= lows[1] and (rate - half) <= lows[2],
        }
    return {
        "levels": rates,
        "order_ok": all(a < b for a, b in zip(ordered, ordered[1:], strict=False)),
        "band_level3": band,
    }


def run(
    histories: Mapping[EventType, TypeHistory | None],
    first_years: Mapping[str, int | None],
    persistent: Mapping[EventType, bool],
    regime_series: Mapping[str, Mapping[int, int]] | None = None,
    include_holdout: bool = False,
    termination: Mapping[str, list[tuple[int, int]]] | None = None,
) -> dict:
    periods = {k: v for k, v in PERIODS.items() if include_holdout or k != "holdout"}
    years = [y for lo, hi in periods.values() for y in range(lo, hi + 1)]
    out: dict = {"periods": periods, "types": {}, "danger": {}}
    all_records: dict[EventType, list[dict]] = {}
    for key, history in histories.items():
        if history is None:
            continue
        records = run_type(
            key, history, first_years, persistent.get(key, False), years, regime_series
        )
        all_records[key] = records
        per_period = {}
        for name, (lo, hi) in periods.items():
            chunk = [r for r in records if lo <= r["year"] <= hi]
            states = sorted({r["state"] for r in chunk})
            per_period[name] = {
                state: summarise([r for r in chunk if r["state"] == state]) for state in states
            }
        out["types"][key.value] = {"lag_years": LAG.get(key, 2), "periods": per_period}
    for name, (lo, hi) in periods.items():
        chunk = {k: [r for r in v if lo <= r["year"] <= hi] for k, v in all_records.items()}
        out["danger"][name] = danger_check(chunk)
    # Conflict onset variants (Fable round 4, #5): plain transitions vs a one-year lull counted
    # as continuing.
    out["conflict_variants"] = {}
    for key in CLASS_A:
        history = histories.get(key)
        if history is None:
            continue
        for gap in (0, 1):
            records = run_type(key, history, first_years, True, years, None, {"gap": gap})
            out["conflict_variants"][f"{key.value}, lull gap {gap}"] = {
                name: {
                    state: summarise(
                        [r for r in records if lo <= r["year"] <= hi and r["state"] == state]
                    )
                    for state in ("onset", "continuation")
                }
                for name, (lo, hi) in periods.items()
            }
    internal = histories.get(EventType.INTERNAL_ARMED_CONFLICT)
    if termination and internal is not None:
        out["termination_variants"] = termination_variants(
            internal, first_years, years, periods, termination
        )
    coups = histories.get(EventType.COUP_ATTEMPT)
    if coups is not None:
        # Variants of the coup base rate, compared on the tuning period (rules: choose on
        # tuning, confirm on validation; every look is logged). The offset variant needs
        # earlier base forecasts to learn from, so base records start in 1992.
        out["coup_variants"] = {}
        early = list(range(1992, min(years))) + years
        bases: dict[str, list[dict]] = {}
        for label, variant in COUP_VARIANTS.items():
            records = run_type(
                EventType.COUP_ATTEMPT, coups, first_years, False, early, regime_series, variant
            )
            if label in OFFSET_BASES:
                bases[label] = records
            out["coup_variants"][label] = _by_period(records, periods)
        for label, records in bases.items():
            for l2 in OFFSET_L2:
                corrected = offset_records(records, LAG[EventType.COUP_ATTEMPT], min(years), l2)
                name = f"offset model on {label}" + ("" if l2 == 20.0 else f", L2 {l2:g}")
                out["coup_variants"][name] = _by_period(corrected, periods)
    return out


def termination_variants(
    history: TypeHistory,
    first_years: Mapping[str, int | None],
    years: list[int],
    periods: Mapping[str, tuple[int, int]],
    termination: Mapping[str, list[tuple[int, int]]],
) -> dict:
    """Internal-conflict onset: base rate vs a trained correction by how the last conflict
    ended (UCDP Conflict Termination; Fable round 4, #5). Only episodes that ended at least
    one year before the data cut-off are used, since an ending is coded after a quiet year."""
    from geointel.risk.sources.ucdp_term import features

    lag = LAG[EventType.INTERNAL_ARMED_CONFLICT]
    early = list(range(1992, min(years))) + years
    records = run_type(EventType.INTERNAL_ARMED_CONFLICT, history, first_years, True, early)
    onset = [
        {**r, "x": features(termination, r["iso3"], r["year"] - lag - 1)}
        for r in records
        if r["state"] == "onset"
    ]
    out = {"base rate": _by_period([r for r in onset if r["year"] >= min(years)], periods)}
    for l2 in OFFSET_L2:
        corrected = offset_records(onset, lag, min(years), l2)
        out[f"ending-of-last-conflict correction, L2 {l2:g}"] = _by_period(corrected, periods)
    return out


def _by_period(records: list[dict], periods: Mapping[str, tuple[int, int]]) -> dict:
    return {
        name: summarise([r for r in records if lo <= r["year"] <= hi])
        for name, (lo, hi) in periods.items()
    }


COUP_VARIANTS = {
    "groups, cap 2x (1.10)": {"groups": "all", "cap": 2.0, "world_cap": None},
    "world prior, no groups": {"groups": None, "cap": None, "world_cap": None},
    "world prior, cap 2x": {"groups": None, "cap": None, "world_cap": 2.0},
    "hybrid: groups for democracies only, world cap 2x": {
        "groups": "democracies",
        "cap": 2.0,
        "world_cap": 2.0,
    },
}
# Run 6 (1.13): the offset model on top of the live hybrid, at two strengths of shrinkage.
OFFSET_BASES = ("world prior, cap 2x", "hybrid: groups for democracies only, world cap 2x")
OFFSET_L2 = (20.0, 50.0)
# The variant used by the live model since 1.11.0 (chosen on the tuning period, run 4).
LIVE_COUP_VARIANT = COUP_VARIANTS["hybrid: groups for democracies only, world cap 2x"]
