"""Backtest on real historical data: what the automated signals alone would have shown.

Unlike ``backtest.py`` (a hand-written timeline), this replays archived GDELT event data and,
for 2021–2022, Sentinel-1 radar through the same thresholds and likelihood ratios as the live
site. No case-specific tuning: the same rules run on every case, including the quiet months.

Run in its own workflow (downloads ~1,500 days of GDELT files): ``python -m geointel.risk
backtest-real``.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta

from geointel.risk.warning_signs import (
    COUP,
    INTERSTATE,
    PROTEST,
    SPEC,
    adjust,
    combine,
)

SCHEMA = "geointel-backtest-real-v1"
BASELINE = 90
MIN_BASE = 45


@dataclass(frozen=True)
class Case:
    key: str
    title_ru: str
    title_en: str
    event: str
    start: str
    target: str
    actor: str | None
    risk: str
    base_annual: float
    monthly: bool = False  # before April 2013 GDELT publishes only monthly files
    sites: tuple[str, ...] = ()


CASES: tuple[Case, ...] = (
    Case(
        "ukraine_2022",
        "Вторжение России в Украину, 24.02.2022",
        "Russia's invasion of Ukraine, 24 Feb 2022",
        "2022-02-24",
        "2021-01-01",
        "UKR",
        "RUS",
        INTERSTATE,
        0.05,
        sites=("yelnya", "klintsy", "belgorod", "brest", "osipovichi"),
    ),
    Case(
        "crimea_2014",
        "Захват Крыма, 27.02.2014",
        "Seizure of Crimea, 27 Feb 2014",
        "2014-02-27",
        "2013-10-01",
        "UKR",
        "RUS",
        INTERSTATE,
        0.02,
    ),
    Case(
        "georgia_2008",
        "Война России и Грузии, 07.08.2008",
        "Russia–Georgia war, 7 Aug 2008",
        "2008-08-07",
        "2008-01-01",
        "GEO",
        "RUS",
        INTERSTATE,
        0.03,
        monthly=True,
    ),
    Case(
        "iran_israel_2024",
        "Прямой удар Ирана по Израилю, 13.04.2024",
        "Iran's direct strike on Israel, 13 Apr 2024",
        "2024-04-13",
        "2023-12-01",
        "ISR",
        "IRN",
        INTERSTATE,
        0.05,
    ),
    Case(
        "israel_iran_2025",
        "Удары Израиля по Ирану, 13.06.2025",
        "Israel's strikes on Iran, 13 Jun 2025",
        "2025-06-13",
        "2025-02-01",
        "IRN",
        "ISR",
        INTERSTATE,
        0.1,
    ),
    Case(
        "niger_2023",
        "Переворот в Нигере, 26.07.2023",
        "Coup in Niger, 26 Jul 2023",
        "2023-07-26",
        "2023-03-01",
        "NER",
        None,
        COUP,
        0.05,
    ),
    Case(
        "kazakhstan_2022",
        "Протесты в Казахстане, 02.01.2022",
        "Protests in Kazakhstan, 2 Jan 2022",
        "2022-01-02",
        "2021-09-01",
        "KAZ",
        None,
        PROTEST,
        0.1,
    ),
)

V1_MONTHLY = "http://data.gdeltproject.org/events/{month}.zip"


def days_needed(case: Case) -> list[date]:
    start = date.fromisoformat(case.start) - timedelta(days=BASELINE + 10)
    end = date.fromisoformat(case.event)
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def months_needed(case: Case) -> list[str]:
    start = date.fromisoformat(case.start) - timedelta(days=BASELINE + 10)
    end = date.fromisoformat(case.event)
    months, cursor = [], date(start.year, start.month, 1)
    while cursor <= end:
        months.append(cursor.strftime("%Y%m"))
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return months


def _share_z(
    days: dict[str, dict], code: str, category: str, at: date, window: int
) -> float | None:
    start = (at - timedelta(days=window)).isoformat()
    base_from = (at - timedelta(days=window + BASELINE)).isoformat()
    recent, base = [], []
    for day, data in days.items():
        if day > at.isoformat() or day < base_from:
            continue
        c = (data.get("countries") or {}).get(code)
        if not c or c.get("all", 0) < 5:
            continue
        (recent if day > start else base).append(c.get(category, 0) / c["all"])
    if len(recent) < max(2, window // 3) or len(base) < (MIN_BASE if window <= 7 else 2):
        return None
    mean = sum(base) / len(base)
    sd = math.sqrt(sum((v - mean) ** 2 for v in base) / max(1, len(base) - 1))
    return round((sum(recent) / len(recent) - mean) / max(sd, 0.2 * mean, 0.005), 2)


def _dyad_ratio(days: dict[str, dict], a: str, b: str, at: date) -> float | None:
    recent_from = (at - timedelta(days=30)).isoformat()
    base_from = (at - timedelta(days=30 + BASELINE)).isoformat()
    recent = base = 0
    base_days = 0
    for day, data in days.items():
        if day > at.isoformat() or day < base_from:
            continue
        dy = data.get("dyads") or {}
        n = dy.get(f"{a}>{b}", 0) + dy.get(f"{b}>{a}", 0)
        if day > recent_from:
            recent += n
        else:
            base += n
            base_days += 1
    if base_days < MIN_BASE:
        return None
    return round((recent + 1) / (base / base_days * 30 + 1), 2)


def signs_at(case: Case, days: dict[str, dict], at: date, radar: dict[str, list] | None) -> list:
    window = 30 if case.monthly else 7
    signs = []
    categories = {
        INTERSTATE: [("external", "gdelt_external")],
        COUP: [
            ("protest", "gdelt_protest"),
            ("repression", "gdelt_repression"),
            ("armed", "gdelt_armed"),
        ],
        PROTEST: [("protest", "gdelt_protest"), ("repression", "gdelt_repression")],
    }[case.risk]
    for category, key in categories:
        z = _share_z(days, case.target, category, at, window)
        if z is not None and z >= 2.5:
            signs.append(
                {"key": key, "status": "active", "strength": 1.5 if z >= 3.5 else 1.0, "z": z}
            )
    if case.actor and not case.monthly:
        ratio = _dyad_ratio(days, case.actor, case.target, at)
        if ratio is not None and ratio >= 2:
            signs.append(
                {"key": "gdelt_external", "status": "active", "strength": 1.0, "dyad_ratio": ratio}
            )
    for site, points in (radar or {}).items():
        from geointel.risk.sources.sentinel import change

        upto = [p for p in points if p[0] <= at.isoformat()]
        result = change(upto)
        if result and result["active"]:
            signs.append({"key": "satellite_change", "status": "active", "site": site})
            break
    return signs


def confirmed_signs(
    case: Case, days: dict[str, dict], at: date, radar: dict[str, list] | None
) -> list:
    """Signs at ``at`` weighed like the live pipeline: a sign not active on at least three of
    the last five days counts at half strength (monthly cases look back five months)."""
    from geointel.risk.warning_signs import CONFIRM_DAYS, FRESH_STRENGTH

    step = timedelta(days=30 if case.monthly else 1)
    counts: dict[str, int] = {}
    for back in range(5):
        for sign in signs_at(case, days, at - back * step, radar):
            counts[sign["key"]] = counts.get(sign["key"], 0) + 1
    signs = signs_at(case, days, at, radar)
    for sign in signs:
        if counts.get(sign["key"], 0) < CONFIRM_DAYS:
            sign["strength"] = sign.get("strength", 1.0) * FRESH_STRENGTH
    return signs


def evaluate(case: Case, days: dict[str, dict], radar: dict[str, list] | None = None) -> dict:
    event = date.fromisoformat(case.event)
    at = date.fromisoformat(case.start)
    step = timedelta(days=30 if case.monthly else 7)
    p1m_base = 1 - (1 - case.base_annual) ** (1 / 12)
    points = []
    while at < event:
        signs = confirmed_signs(case, days, at, radar)
        combined = combine(signs, case.risk)
        points.append(
            {
                "date": at.isoformat(),
                "factor": combined["factor"],
                "p1m": round(adjust(p1m_base, combined["factor"]), 4),
                "p1y": round(adjust(case.base_annual, combined["factor"]), 4),
                "signs": sorted({s["key"] for s in signs}),
            }
        )
        at += step
    elevated = [p for p in points if p["factor"] > 1.05]
    first = None  # start of the final unbroken run of elevated points before the event
    for i, p in enumerate(points):
        if all(q["factor"] > 1.05 for q in points[i:]):
            first = p["date"]
            break
    brier = [
        (p["p1m"] - (1 if 0 <= (event - date.fromisoformat(p["date"])).days <= 30 else 0)) ** 2
        for p in points
    ]
    brier_base = [
        (p1m_base - (1 if 0 <= (event - date.fromisoformat(p["date"])).days <= 30 else 0)) ** 2
        for p in points
    ]
    return {
        "key": case.key,
        "title_ru": case.title_ru,
        "title_en": case.title_en,
        "event_date": case.event,
        "risk": case.risk,
        "target": case.target,
        "base_annual": case.base_annual,
        "monthly": case.monthly,
        "points": points,
        "lead_days": (event - date.fromisoformat(first)).days if first else 0,
        "elevated_weeks": len(elevated),
        "max_factor": max((p["factor"] for p in points), default=1.0),
        "brier": round(sum(brier) / len(brier), 5) if brier else None,
        "brier_base": round(sum(brier_base) / len(brier_base), 5) if brier_base else None,
        "radar": bool(radar),
    }


def report(results: list[dict], generated_at: str) -> dict:
    return {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "lr": {
            k: SPEC[k].lr
            for k in (
                "gdelt_external",
                "gdelt_protest",
                "gdelt_repression",
                "gdelt_armed",
                "satellite_change",
            )
        },
        "cases": results,
    }
