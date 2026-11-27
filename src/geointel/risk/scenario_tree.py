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
from dataclasses import dataclass, replace

MONTHS = 120


@dataclass(frozen=True)
class Ramp:
    """Multipliers of the current hazard. Times are in years."""

    war_late: float  # extra risk reached by year 8 if the war continues (from year 4)
    cease_points: tuple[tuple[float, float], ...]  # (years after ceasefire, multiplier)
    us_weak: float  # multiplier once US guarantees weaken
    rearm_share: float = 0.5  # share of the increase kept, since Europe is rearming


RAMPS = {
    "russia_nato": Ramp(
        war_late=1.5,
        cease_points=((0.0, 1.0), (0.5, 1.0), (2.0, 1.6), (5.0, 2.2)),
        us_weak=1.5,
    ),
    "russia_nato_war": Ramp(
        war_late=1.3,
        cease_points=((0.0, 1.0), (2.0, 1.0), (5.0, 2.5)),
        us_weak=2.0,
    ),
}

BASIS_RU = (
    "Дерево сценариев: риск этого года умножается на коэффициенты в зависимости от того, "
    "остановится ли война в Украине и ослабнут ли гарантии США. Сроки взяты из оценок разведок "
    "Дании (2025: локальная война через полгода после прекращения огня, угроза Балтии через два "
    "года, большая война через пять лет) и Литвы (2026: ограниченный конфликт через 6–10 лет, "
    "если война продолжится). Сами коэффициенты — суждение GeoIntel; поскольку Европа "
    "перевооружается, а сроки описывают возможности, а не намерения, учитываем половину роста, "
    "заложенного в этих сроках. Прекращение огня и ослабление гарантий США считаем "
    "независимыми событиями."
)
BASIS_EN = (
    "Scenario tree: this year's risk is multiplied by factors that depend on whether the war in "
    "Ukraine stops and whether US guarantees weaken. Timelines come from Danish intelligence "
    "(2025: a local war six months after a ceasefire, a threat to the Baltics in two years, a "
    "large war in five) and Lithuanian intelligence (2026: a limited conflict in 6–10 years if the "
    "war continues). The multipliers are GeoIntel judgement; because Europe is rearming and the "
    "timelines describe capability rather than intent, we keep half of the increase they imply. "
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


SIGN_HALF_LIFE_MONTHS = 6  # today's warning signs say less and less about later years


def _base_annual(item: dict) -> float:
    """The pooled annual hazard without today's warning-sign factor."""
    p = min(max(item["annual"]["p"], 1e-6), 1 - 1e-6)
    factor = item.get("indicator_factor") or 1.0
    odds = p / (1 - p) / factor
    return odds / (1 + odds)


def simulate(
    key: str,
    annual: float,
    ceasefire_annual: float,
    us_weak_annual: float,
    sign_factor: float = 1.0,
    ramp: Ramp | None = None,
) -> dict[str, object]:
    """``annual`` is the hazard without warning signs; ``sign_factor`` (today's signs) fades
    with a half-life of six months."""
    ramp = ramp or RAMPS[key]
    monthly = -math.log(max(1 - annual, 1e-6)) / 12
    fade = [sign_factor ** (0.5 ** (m / SIGN_HALF_LIFE_MONTHS)) for m in range(MONTHS)]
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
                hazard += monthly * multiplier(ramp, m, c, w) * fade[m]
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


SENSITIVITY_RU = {
    "annual": "Нынешний годовой риск (пул источников), вдвое ниже или выше",
    "rearm_share": "Доля роста угрозы, которую не перекрывает перевооружение Европы",
    "ceasefire": "Годовая вероятность прекращения огня в Украине",
    "us_weak": "Годовая вероятность ослабления гарантий США",
    "cease_ramp": "Рост угрозы после прекращения огня (оценки разведок)",
    "us_ramp": "Рост угрозы при ослаблении гарантий США",
}
SENSITIVITY_EN = {
    "annual": "Current yearly risk (pooled sources), halved or doubled",
    "rearm_share": "Share of the threat increase not offset by European rearmament",
    "ceasefire": "Yearly probability of a ceasefire in Ukraine",
    "us_weak": "Yearly probability of weaker US guarantees",
    "cease_ramp": "Threat growth after a ceasefire (intelligence timelines)",
    "us_ramp": "Threat growth if US guarantees weaken",
}


def sensitivity(key: str, annual: float, cease: float, weak: float, factor: float) -> list[dict]:
    """How the 5- and 10-year results move when each judgement parameter is set to the low
    and high end of a plausible range (one at a time)."""
    ramp = RAMPS[key]
    scaled = lambda pts, k: tuple((x, 1 + (y - 1) * k) for x, y in pts)  # noqa: E731
    variants = {
        "rearm_share": (
            (0.25, replace(ramp, rearm_share=0.25), cease, weak),
            (0.75, replace(ramp, rearm_share=0.75), cease, weak),
        ),
        "ceasefire": (
            (cease / 2, ramp, cease / 2, weak),
            (min(cease * 1.5, 0.95), ramp, min(cease * 1.5, 0.95), weak),
        ),
        "us_weak": (
            (weak / 2, ramp, cease, weak / 2),
            (min(weak * 2, 0.95), ramp, cease, min(weak * 2, 0.95)),
        ),
        "cease_ramp": (
            (0.5, replace(ramp, cease_points=scaled(ramp.cease_points, 0.5)), cease, weak),
            (1.5, replace(ramp, cease_points=scaled(ramp.cease_points, 1.5)), cease, weak),
        ),
        "us_ramp": (
            (1.0, replace(ramp, us_weak=1.0), cease, weak),
            (2.0, replace(ramp, us_weak=ramp.us_weak * 4 / 3), cease, weak),
        ),
    }
    rows = []
    annuals = {"annual": (annual / 2, min(annual * 2, 0.99))}
    variants["annual"] = (
        (annual / 2, ramp, cease, weak),
        (min(annual * 2, 0.99), ramp, cease, weak),
    )
    for name, ((lo_v, lo_r, lo_c, lo_w), (hi_v, hi_r, hi_c, hi_w)) in variants.items():
        lo_a, hi_a = annuals.get(name, (annual, annual))
        lo = simulate(key, lo_a, lo_c, lo_w, factor, lo_r)
        hi = simulate(key, hi_a, hi_c, hi_w, factor, hi_r)
        rows.append(
            {
                "param": name,
                "label_ru": SENSITIVITY_RU[name],
                "label_en": SENSITIVITY_EN[name],
                "values": [round(lo_v, 3), round(hi_v, 3)],
                "p5y": [lo["p5y"], hi["p5y"]],
                "p10y": [lo["p10y"], hi["p10y"]],
            }
        )
    rows.sort(key=lambda r: -abs(r["p10y"][1] - r["p10y"][0]))
    return rows


def apply_trees(scenarios: list[dict]) -> None:
    """Replace constant-hazard 5- and 10-year figures of tree scenarios with tree results."""
    by_key = {s["key"]: s for s in scenarios}
    cease = _base_annual(by_key["ukraine_ceasefire"]) if "ukraine_ceasefire" in by_key else 0.25
    weak = _base_annual(by_key["us_guarantee"]) if "us_guarantee" in by_key else 0.1
    for key in RAMPS:
        item = by_key.get(key)
        if item is None:
            continue
        factor = item.get("indicator_factor") or 1.0
        base = _base_annual(item)
        scale = base / max(item["annual"]["p"], 1e-9)
        # The first year must equal what the site shows for "1 year" (the monthly profile);
        # the tree only shapes the following years (1.4.0: they disagreed, 5.8% vs 6.9%).
        target = (item.get("horizons", {}).get("1y") or {}).get("p")
        calib = 1.0
        if target:
            first = simulate(key, min(item["annual"]["p"] * scale, 0.99), cease, weak, factor)
            calib = target / max(first["p1y"], 1e-9)
        runs = {
            name: simulate(
                key, min(item["annual"][name] * scale * calib, 0.99), cease, weak, factor
            )
            for name in ("p", "low", "high")
        }
        sens = sensitivity(key, min(item["annual"]["p"] * scale * calib, 0.99), cease, weak, factor)
        for horizon, field in (("5y", "p5y"), ("10y", "p10y")):
            mid = runs["p"][field]
            spread = [v for r in sens for v in r[field]]
            item["horizons"][horizon] = {
                "p": mid,
                "low": min(runs["low"][field], mid, *spread),
                "high": max(runs["high"][field], mid, *spread),
            }
        item["tree"] = {
            "inputs": {
                "annual_now": item["annual"]["p"],
                "annual_base": round(base, 4),
                "sign_factor": factor,
                "ceasefire_annual": round(cease, 4),
                "us_weak_annual": round(weak, 4),
                "year1_calibration": round(calib, 3),
            },
            "yearly": runs["p"]["yearly"],
            "branches": runs["p"]["branches"],
            "sensitivity": sens,
            "basis_ru": BASIS_RU,
            "basis_en": BASIS_EN,
        }
