"""Month-by-month risk for the next twelve months instead of an even split of the yearly figure.

Risk is not spread evenly over a year. Three things move individual months:

* today's warning signs say most about the next weeks: their effect halves every three months;
* known dates (end of a truce, an election, a court ruling, a large exercise) raise the months
  they fall in, by a multiplier stated next to the date;
* for ground operations in Eastern Europe the spring and autumn mud seasons lower the risk a
  little (GeoIntel judgement, ×0.8 in March–April and November).

The one-month and one-year horizons of each scenario are then read from this profile.
"""

import math
from datetime import date, timedelta

from geointel.risk.scenario_types import Scenario

SIGN_HALF_LIFE_MONTHS = 3
MUD = {3: 0.8, 4: 0.8, 11: 0.8}
STAGES = (
    (3, {"final"}),
    (2, {"personnel", "logistics"}),
    (1, {"posture", "pretext", "cyber"}),
)


def base_annual(item: dict) -> float:
    p = min(max(item["annual"]["p"], 1e-6), 1 - 1e-6)
    factor = item.get("indicator_factor") or 1.0
    odds = p / (1 - p) / factor
    return odds / (1 + odds)


def stage(groups: list[str]) -> int:
    present = set(groups)
    for level, needed in STAGES:
        if present & needed:
            return level
    return 0


def _month_start(today: date, offset: int) -> date:
    year, month = today.year, today.month + offset
    year += (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, 1)


def profile(item: dict, scenario: Scenario, today: date) -> list[dict]:
    base = base_annual(item)
    monthly = -math.log(max(1 - base, 1e-6)) / 12
    factor = item.get("indicator_factor") or 1.0
    rows = []
    for m in range(12):
        start = today + timedelta(days=round(30.4 * m))
        end = start + timedelta(days=30)
        mult, why_ru, why_en = factor ** (0.5 ** (m / SIGN_HALF_LIFE_MONTHS)), [], []
        if abs(factor - 1) > 0.02 and m < 3:
            word = "выше" if factor > 1 else "ниже"
            why_ru.append(f"текущие признаки: риск {word} обычного")
            why_en.append(f"current signs: risk {'above' if factor > 1 else 'below'} usual")
        for d in scenario.key_dates:
            if date.fromisoformat(d.start) < end and date.fromisoformat(d.end) >= start:
                mult *= d.multiplier
                why_ru.append(d.label_ru)
                why_en.append(d.label_en)
        if scenario.mud_season and start.month in MUD:
            mult *= MUD[start.month]
            why_ru.append("распутица")
            why_en.append("mud season")
        p = 1 - math.exp(-monthly * mult)
        rows.append(
            {
                "month": _month_start(today, m).isoformat()[:7] if m else today.isoformat()[:7],
                "from": start.isoformat(),
                "p": round(p, 4),
                "multiplier": round(mult, 3),
                "why_ru": why_ru,
                "why_en": why_en,
            }
        )
    return rows


def apply_profiles(results: list[dict], catalogue: dict[str, Scenario], today: date) -> None:
    from geointel.risk.warning_signs import alert_level

    for item in results:
        scenario = catalogue[item["key"]]
        rows = profile(item, scenario, today)
        p1m = rows[0]["p"]
        p1y = 1 - math.prod(1 - r["p"] for r in rows)
        old_1y = max(item["horizons"]["1y"]["p"], 1e-9)
        old_1m = max(item["horizons"]["1m"]["p"], 1e-9)
        for horizon, new, old in (("1m", p1m, old_1m), ("1y", p1y, old_1y)):
            h = item["horizons"][horizon]
            ratio = new / old
            item["horizons"][horizon] = {
                "p": round(new, 4),
                "low": round(min(h["low"] * ratio, new), 4),
                "high": round(max(min(h["high"] * ratio, 0.999), new), 4),
            }
        item["profile"] = rows
        item["stage"] = stage(item.get("sign_groups", []))
        base_month = 1 - (1 - base_annual(item)) ** (1 / 12)
        ratio = p1m / max(base_month, 1e-9)
        item["alert"] = (
            {
                "level": alert_level(p1m, ratio, item["stage"] == 3),
                "p1m": round(p1m, 4),
                "ratio": round(ratio, 2),
            }
            if item["polarity"] > 0
            else None
        )
