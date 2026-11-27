"""ViEWS (Uppsala / PRIO) country-month conflict forecasts.

The public API lists forecast runs at its root (``fatalities003_2026_09_t01`` …) and serves
state-based forecasts per country and month at ``/<run>/cm/sb``. ``main_dich`` is the
probability of at least 25 state-based battle-related deaths in that country and month.

GeoIntel uses ViEWS as the base for internal armed conflict onset (plan, stage 2):
log-odds average with weight 0.7 for ViEWS and 0.3 for the GeoIntel model, applied only to
countries that are not already in an active conflict (onset questions).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from datetime import date

SOURCE = "ViEWS conflict forecasts (Uppsala University / PRIO), CC BY 4.0"
API = "https://api.viewsforecasting.org"
RUN_RE = re.compile(r"^fatalities(\d{3})_(\d{4})_(\d{2})_t01$")
VIEWS_WEIGHT = 0.7
EPS = 1e-4


def latest_run(runs: Iterable[str]) -> str | None:
    """Newest monthly run: highest (year, month), then highest model generation."""
    best: tuple[int, int, int] | None = None
    name = None
    for run in runs:
        match = RUN_RE.match(str(run))
        if not match:
            continue
        key = (int(match.group(2)), int(match.group(3)), int(match.group(1)))
        if best is None or key > best:
            best, name = key, str(run)
    return name


def runs_from_root(payload) -> list[str]:
    if isinstance(payload, Mapping):
        payload = payload.get("runs") or payload.get("data") or list(payload)
    return [str(r) for r in payload or []]


def compact(rows: Iterable[Mapping]) -> dict[str, dict[str, float]]:
    """{ISO3: {"YYYY-MM": p}} from API rows; rows without ISO3 or probability are skipped."""
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        iso3 = str(row.get("isoab") or "").upper()
        p = row.get("main_dich")
        year, month = row.get("year"), row.get("month")
        if len(iso3) != 3 or p is None or not year or not month:
            continue
        out.setdefault(iso3, {})[f"{int(year):04d}-{int(month):02d}"] = float(p)
    return out


def _months_from(start: date, count: int) -> list[str]:
    keys = []
    year, month = start.year, start.month
    for _ in range(count):
        keys.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return keys


def country_view(months: Mapping[str, float], today: date) -> dict | None:
    """1-month and 12-month probabilities for one country from its monthly series.

    The 12-month figure lies between the highest single month (months fully dependent) and
    the union under independence; the point is their log-odds midpoint and both ends form
    the range. Months already past are ignored; if the run does not cover the current month
    the country is skipped rather than guessed.
    """
    keys = _months_from(today.replace(day=1), 12)
    if keys[0] not in months:
        return None
    series = [months[k] for k in keys if k in months]
    if len(series) < 6:
        return None
    p1m = _clip(series[0])
    low = _clip(max(series))
    high = _clip(1 - math.prod(1 - _clip(p) for p in series))
    mid = _expit((_logit(low) + _logit(high)) / 2)
    return {
        "p1m": round(p1m, 4),
        "p12m": round(mid, 4),
        "p12m_low": round(low, 4),
        "p12m_high": round(high, 4),
        "months": len(series),
    }


def _clip(p: float) -> float:
    return min(max(float(p), EPS), 1 - EPS)


def _logit(p: float) -> float:
    p = _clip(p)
    return math.log(p / (1 - p))


def _expit(x: float) -> float:
    x = max(min(x, 35.0), -35.0)
    return 1 / (1 + math.exp(-x))


def blend(views_p: float, own_p: float, weight: float = VIEWS_WEIGHT) -> float:
    """Weighted mean of log-odds (ViEWS weight, GeoIntel 1 - weight)."""
    return _expit(weight * _logit(views_p) + (1 - weight) * _logit(own_p))


def apply_views(snapshot: dict, payload: Mapping | None, today: date, key: str) -> int:
    """Blend ViEWS into the onset horizons of ``key`` for countries not in active conflict.

    1m and 1y use the ViEWS monthly and 12-month probabilities directly; 5y and 10y extend
    the ViEWS 12-month figure as a constant annual hazard before blending, as the GeoIntel
    model does for its own base rate. Ranges blend low with low and high with high. Every
    blended country keeps the original GeoIntel numbers and the ViEWS numbers for display.
    Returns the number of countries blended.
    """
    from geointel.risk.model import onset_within

    if not payload:
        return 0
    data = payload.get("countries") or {}
    run = payload.get("run")
    count = 0
    for country in snapshot.get("countries", []):
        risk = (country.get("risks") or {}).get(key)
        months = data.get(country.get("iso3"))
        if not risk or not months:
            continue
        view = country_view(months, today)
        if not view:
            continue
        country.setdefault("external", {})["views"] = {**view, "run": run}
        if risk.get("question") != "onset_within":
            continue
        horizons = risk.get("horizons") or {}
        own = {h: dict(v) for h, v in horizons.items()}
        targets = {
            "1m": (view["p1m"], view["p1m"], view["p1m"]),
            "1y": (view["p12m"], view["p12m_low"], view["p12m_high"]),
        }
        for h, years in (("5y", 5.0), ("10y", 10.0)):
            targets[h] = (
                onset_within(view["p12m"], years),
                onset_within(view["p12m_low"], years),
                onset_within(view["p12m_high"], years),
            )
        previous = 0.0
        for h in ("1m", "1y", "5y", "10y"):
            if h not in horizons or h not in targets:
                continue
            vp, vl, vh = targets[h]
            cell = horizons[h]
            p = max(blend(vp, cell["p"]), previous)
            low = min(blend(vl, cell.get("low", cell["p"])), p)
            high = max(blend(vh, cell.get("high", cell["p"])), p)
            horizons[h] = {**cell, "p": round(p, 4), "low": round(low, 4), "high": round(high, 4)}
            previous = p
        risk["model"] = "views_blend"
        risk["own_horizons"] = own
        count += 1
    for entry in snapshot.get("event_types", []):
        if entry.get("key") == key and count:
            entry["views"] = {"run": run, "weight": VIEWS_WEIGHT, "countries": count}
    return count
