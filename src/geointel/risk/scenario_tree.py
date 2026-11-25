"""Scenario tree for Russia–NATO: the yearly risk is not constant but depends on how the war in
Ukraine ends, whether US guarantees weaken, and how fast Russia rebuilds its forces.

The tree is a monthly simulation over ten years with two uncertain events:

* ``C`` - a general ceasefire in Ukraine (rate taken from the ``ukraine_ceasefire`` scenario);
* ``U`` - a weakening of US guarantees (rate taken from the ``us_guarantee`` scenario).

The current annual hazard of the scenario (already pooled from history, experts, markets,
official judgements and the warning-sign factor) applies to today's state: war continuing, US
guarantees in place. It is then multiplied by a capability ramp built from published timelines:

* Danish intelligence (February 2025): after the fighting stops Russia could wage a local war
  within ~6 months, threaten NATO's Baltic states within ~2 years and fight a large-scale war in
  Europe within ~5 years - assuming NATO does not rearm at the same pace and without US help;
* Lithuanian intelligence (March 2026): if the war continues, readiness for a limited regional
  conflict in 6-10 years; with sanctions lifted, a wide-scale conflict in about 6 years.

The multipliers themselves are GeoIntel judgement and are shown on the site next to the result.
"""

import math
from dataclasses import dataclass

MONTHS = 120


@dataclass(frozen=True)
class Ramp:
    """Multipliers of the current hazard. Times are in years."""

    war_late: float  # extra risk reached by year 8 if the war continues (from year 4)
    cease_points: tuple[tuple[float, float], ...]  # (years after ceasefire, multiplier)
    us_weak: float  # multiplier once US guarantees weaken
    rearm_share: float = 0.6  # share of the increase kept, since Europe is rearming


RAMPS = {
    "russia_nato": Ramp(
        war_late=1.5,
        cease_points=((0.0, 1.0), (0.5, 1.0), (2.0, 1.8), (5.0, 2.5)),
        us_weak=1.5,
    ),
    "russia_nato_war": Ramp(
        war_late=1.3,
        cease_points=((0.0, 1.0), (2.0, 1.0), (5.0, 3.0)),
        us_weak=2.0,
    ),
}

BASIS_RU = (
    "Дерево сценариев: риск этого года умножается на коэффициенты в зависимости от того, "
    "остановится ли война в Украине и ослабнут ли гарантии США. Сроки взяты из оценок разведок "
    "Дании (2025: локальная война через полгода после прекращения огня, угроза Балтии через два "
    "года, большая война через пять лет) и Литвы (2026: ограниченный конфликт через 6–10 лет, "
    "если война продолжится). Сами коэффициенты — суждение GeoIntel; поскольку Европа "
    "перевооружается, а сроки описывают возможности, а не намерения, учитываем 60% роста, "
    "заложенного в этих сроках. Прекращение огня и ослабление гарантий США считаем "
    "независимыми событиями."
)
BASIS_EN = (
    "Scenario tree: this year's risk is multiplied by factors that depend on whether the war in "
    "Ukraine stops and whether US guarantees weaken. Timelines come from Danish intelligence "
    "(2025: a local war six months after a ceasefire, a threat to the Baltics in two years, a "
    "large war in five) and Lithuanian intelligence (2026: a limited conflict in 6–10 years if the "
    "war continues). The multipliers are GeoIntel judgement; because Europe is rearming and the "
    "timelines describe capability rather than intent, we keep 60% of the increase they imply. "
    "A ceasefire and a weakening of US guarantees are treated as independent events."
)


def _interp(points: tuple[tuple[float, float], ...], x: float) -> float:
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def multiplier(ramp: Ramp, month: int, cease: int | None, weak: int | None) -> float:
    years = month / 12
    if cease is None or month < cease:
        base = 1.0 + (ramp.war_late - 1.0) * min(max((years - 4) / 4, 0.0), 1.0)
    else:
        base = _interp(ramp.cease_points, (month - cease) / 12)
    if weak is not None and month >= weak:
        base *= ramp.us_weak
    return 1.0 + (base - 1.0) * ramp.rearm_share


def _event_months(annual: float) -> list[tuple[int | None, float]]:
    """Distribution of the month an event first happens (None: not within the horizon)."""
    rate = -math.log(max(1 - annual, 1e-6)) / 12
    survive = 1.0
    out: list[tuple[int | None, float]] = []
    for m in range(MONTHS):
        p = survive * (1 - math.exp(-rate))
        out.append((m, p))
        survive -= p
    out.append((None, survive))
    return out


def _coarse(dist: list[tuple[int | None, float]], step: int = 3) -> list[tuple[int | None, float]]:
    """Group months into quarters to keep the double sum fast."""
    grouped: dict[int | None, float] = {}
    for m, p in dist:
        key = None if m is None else (m // step) * step + step // 2
        grouped[key] = grouped.get(key, 0.0) + p
    return list(grouped.items())


def simulate(
    key: str, annual: float, ceasefire_annual: float, us_weak_annual: float
) -> dict[str, object]:
    ramp = RAMPS[key]
    monthly = -math.log(max(1 - annual, 1e-6)) / 12
    cease_dist = _coarse(_event_months(ceasefire_annual))
    weak_dist = _coarse(_event_months(us_weak_annual))
    cum = [0.0] * (MONTHS + 1)  # P(event by month m)
    branches: dict[tuple[str, str], list[float]] = {}
    for c, pc in cease_dist:
        c_label = "war" if c is None else "cease_early" if c < 24 else "cease_late"
        for w, pw in weak_dist:
            w_label = "us_firm" if w is None else "us_weak"
            weight = pc * pw
            hazard = 0.0
            row = branches.setdefault((c_label, w_label), [0.0, 0.0, 0.0])
            row[0] += weight
            for m in range(MONTHS):
                hazard += monthly * multiplier(ramp, m, c, w)
                p_event = 1 - math.exp(-hazard)
                cum[m + 1] += weight * p_event
                if m + 1 == 60:
                    row[1] += weight * p_event
            row[2] += weight * (1 - math.exp(-hazard))
    yearly = []
    for year in range(1, 11):
        before = cum[(year - 1) * 12]
        now = cum[year * 12]
        yearly.append(
            {
                "year": year,
                "cumulative": round(now, 4),
                "annual": round((now - before) / max(1 - before, 1e-9), 4),
            }
        )
    rows = []
    for (c_label, w_label), (weight, p5, p10) in sorted(branches.items()):
        rows.append(
            {
                "ukraine": c_label,
                "us": w_label,
                "weight": round(weight, 4),
                "p5y": round(p5 / weight, 4) if weight else 0.0,
                "p10y": round(p10 / weight, 4) if weight else 0.0,
            }
        )
    return {
        "p1y": round(cum[12], 4),
        "p5y": round(cum[60], 4),
        "p10y": round(cum[120], 4),
        "yearly": yearly,
        "branches": rows,
    }


def apply_trees(scenarios: list[dict]) -> None:
    """Replace constant-hazard 5- and 10-year figures of tree scenarios with tree results."""
    by_key = {s["key"]: s for s in scenarios}
    cease = by_key.get("ukraine_ceasefire", {}).get("annual", {}).get("p", 0.25)
    weak = by_key.get("us_guarantee", {}).get("annual", {}).get("p", 0.1)
    for key in RAMPS:
        item = by_key.get(key)
        if item is None:
            continue
        annual = item["annual"]
        mid = simulate(key, annual["p"], cease, weak)
        low = simulate(key, annual["low"], cease, weak)
        high = simulate(key, annual["high"], cease, weak)
        for horizon, field in (("5y", "p5y"), ("10y", "p10y")):
            item["horizons"][horizon] = {
                "p": mid[field],
                "low": min(low[field], mid[field]),
                "high": max(high[field], mid[field]),
            }
        item["tree"] = {
            "inputs": {
                "annual_now": annual["p"],
                "ceasefire_annual": cease,
                "us_weak_annual": weak,
            },
            "yearly": mid["yearly"],
            "branches": mid["branches"],
            "basis_ru": BASIS_RU,
            "basis_en": BASIS_EN,
        }
