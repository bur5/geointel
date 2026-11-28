"""Absolute danger level (1–5) per country, separate from the relative alert ("trend").

The level answers "how dangerous is it here", and it alone drives advice to residents,
travellers, business and people relocating. Whether things got worse than usual is shown
separately as a trend arrow and never changes the level.

Rules (review rounds 2–3, model 1.2.0):

* each event type has a severity class: A (threat to many lives), B (sharp disruption),
  C (inconvenience or local danger);
* the level of a type follows its 12-month probability with class-specific thresholds; the
  1-month probability ×12 is used when higher, so short spikes show;
* natural hazards are regional, so at country scale they do not raise the level; they are
  listed as regional notes until regional estimates exist;
* an ongoing war is a fact, not a probability: a war-intensity conflict (1,000+ battle
  deaths a year) gives level 4, a minor one 3 (internal: 2, it is usually regional), and a
  country fighting only abroad gets 2;
* level 5 is reserved for regions with fighting (needs regional data);
* foreign-ministry advice: the lower median of the available ministries (scale 1–4) may
  raise the model level by one step at most and never lowers it; a gap of two steps or
  more is shown explicitly;
* risks the model does not measure (arbitrary detention of foreigners, terrorism,
  kidnapping, crime) are listed separately from the level.
"""

import re
from collections.abc import Iterable, Mapping

LEVELS = (1, 2, 3, 4, 5)

CLASS = {
    "interstate_conflict": "A",
    "internal_armed_conflict": "A",
    "major_earthquake": "A",
    "tsunami": "A",
    "coup_attempt": "B",
    "humanitarian_crisis": "B",
    "tropical_cyclone": "B",
    "flood": "B",
    "volcano": "B",
    "mass_protest": "C",
    "political_crisis": "C",
    "economic_crisis": "C",
    "drought": "C",
    "wildfire": "C",
}
HAZARDS = frozenset(
    {"major_earthquake", "tsunami", "tropical_cyclone", "flood", "volcano", "drought", "wildfire"}
)
# Lower bounds of levels 2, 3, 4 for the 12-month probability.
# Class A starts at 2%, not 1%: the base model gives every peaceful country about 1.3% a year
# of internal conflict onset (shrinkage to the world mean), which is not a signal.
THRESHOLDS = {"A": (0.02, 0.05, 0.20), "B": (0.03, 0.15, 2.0), "C": (0.15, 2.0, 2.0)}
# Natural hazards strike regions, not whole countries: at country scale they do not raise the
# level; they are listed as regional notes until regional estimates replace them.
HAZARD_CAP = 1
# Countries whose current interstate wars are fought abroad (expeditionary strikes).
EXPEDITIONARY = frozenset({"USA", "GBR", "FRA", "CAN", "AUS"})

ONSET_CAP = 3
REGIONAL_FLOOR_CAP = 4
WAR_KIND = {"interstate_conflict": "interstate", "internal_armed_conflict": "internal"}

NAMES = {
    "ru": {1: "Обычный", 2: "Повышенный", 3: "Высокий", 4: "Очень высокий", 5: "Чрезвычайный"},
    "en": {1: "Normal", 2: "Elevated", 3: "High", 4: "Very high", 5: "Extreme"},
}

# Pattern → (ru, en) for risks to foreigners mentioned by foreign ministries. Patterns are
# whole-word regular expressions (1.12.0): plain substrings matched "mines" inside
# "determines", and "crime" or "health" appear in almost every advisory, so those two tags
# now need wording that says the risk is elevated, not just a mention.
FOREIGNER_TAGS = (
    (
        (
            r"\bwrongful(ly)? detain",
            r"\barbitrar(y|ily) (detain|detention|arrest)",
            r"\bdetain(ed|s|ing)?\b",
            r"\bdetention\b",
        ),
        "detention",
        "произвольные задержания иностранцев",
        "arbitrary detention of foreigners",
    ),
    ((r"\bterror(ism|ist|ists)?\b",), "terrorism", "терроризм", "terrorism"),
    ((r"\bkidnap", r"\bhostages?\b"), "kidnapping", "похищения", "kidnapping"),
    (
        (
            r"\b(violent|serious|high levels? of|widespread|organi[sz]ed) crime\b",
            r"\bcrime (is|remains|rates? (is|are|remain)) (high|common|widespread|prevalent)",
            r"\b(armed robbery|carjacking|express kidnapping)",
        ),
        "crime",
        "преступность",
        "crime",
    ),
    (
        (r"\bcivil unrest\b", r"\bunrest\b", r"\bdemonstrations?\b", r"\bprotests?\b"),
        "unrest",
        "беспорядки и протесты",
        "civil unrest",
    ),
    (
        (
            r"\b(disease )?outbreaks?\b",
            r"\b(epidemic|cholera|ebola|mpox|marburg|plague)\b",
            r"\b(limited|inadequate|poor) (medical|health ?care)",
        ),
        "health",
        "угрозы здоровью",
        "health risks",
    ),
    (
        (r"\blandmines?\b", r"\bunexploded\b", r"\bmines?\b"),
        "mines",
        "мины и неразорвавшиеся боеприпасы",
        "landmines and unexploded ordnance",
    ),
)
_TAG_RES = tuple(
    (re.compile("|".join(words)), key, ru, en) for words, key, ru, en in FOREIGNER_TAGS
)


def type_level(risk: str, p12: float) -> int:
    lows = THRESHOLDS[CLASS[risk]]
    level = 1 + sum(1 for x in lows if p12 >= x)
    return min(level, HAZARD_CAP) if risk in HAZARDS else level


def _horizons(country: Mapping, adjusted: Mapping, risk: str) -> Mapping | None:
    item = adjusted.get(risk) or {}
    if item.get("horizons"):
        return item["horizons"]
    return ((country.get("risks") or {}).get(risk) or {}).get("horizons")


def annualised(horizons: Mapping) -> float:
    year = horizons.get("1y", {}).get("p", 0.0)
    month = horizons.get("1m", {}).get("p", 0.0)
    return max(year, min(1.0, 12 * month))


def war_level(iso3: str, kind: str, intensity: int) -> int:
    if kind == "interstate":
        if iso3 in EXPEDITIONARY:
            return 2
        return 4 if intensity >= 2 else 3
    return 4 if intensity >= 2 else 2


def severity_level(severity: Mapping | None) -> int:
    """INFORM Severity 1–5 → danger level (4+ → 3, else 2); without severity data 2."""
    # Humanitarian crises are severity class B: at most level 3 (1.9.2). INFORM scores a
    # crisis, which often affects some regions or groups, not the whole country.
    score = (severity or {}).get("score")
    if score is None:
        return 2
    return 3 if score >= 4 else 2


def ministry_levels(country: Mapping) -> list[dict]:
    result = []
    us = country.get("advisory") or {}
    if us.get("level"):
        result.append({"key": "us", "level": int(us["level"]), "url": us.get("url")})
    uk = country.get("advisory_uk") or {}
    if uk.get("level"):
        result.append({"key": "uk", "level": int(uk["level"]), "url": uk.get("url")})
    for key, item in sorted((country.get("advisories") or {}).items()):
        if item and item.get("level"):
            result.append({"key": key, "level": int(item["level"]), "url": item.get("url")})
    return result


def lower_median(values: Iterable[int]) -> int | None:
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[(len(ordered) - 1) // 2]


def foreigner_risks(country: Mapping) -> list[dict]:
    texts = [str((country.get("advisory") or {}).get("summary") or "")]
    texts += [str(x) for x in (country.get("advisory_uk") or {}).get("restrictions") or []]
    for item in (country.get("advisories") or {}).values():
        texts.append(str((item or {}).get("summary") or ""))
    text = " ".join(texts).lower()
    return [
        {"key": key, "ru": ru, "en": en}
        for pattern, key, ru, en in _TAG_RES
        if pattern.search(text)
    ]


def trend(alert: Mapping | None) -> dict:
    ratio = float((alert or {}).get("ratio") or 1.0)
    direction = "up" if ratio >= 1.5 else "down" if ratio <= 1 / 1.5 else "flat"
    return {"direction": direction, "ratio": round(ratio, 2), "risk": (alert or {}).get("risk")}


def country_danger(
    country: Mapping,
    adjusted: Mapping | None = None,
    intensity: Mapping[str, int] | None = None,
    alert: Mapping | None = None,
) -> dict:
    iso3 = country["iso3"]
    adjusted = adjusted or {}
    intensity = intensity or {}
    drivers: list[dict] = []
    for risk in CLASS:
        state = (country.get("risks") or {}).get(risk) or {}
        kind = WAR_KIND.get(risk)
        if kind and state.get("active"):
            level = war_level(iso3, kind, intensity.get(kind, 1))
            drivers.append(
                {
                    "risk": risk,
                    "class": CLASS[risk],
                    "level": level,
                    "active": True,
                    "intensity": intensity.get(kind, 1),
                    "abroad": kind == "interstate" and iso3 in EXPEDITIONARY,
                }
            )
            continue
        if risk == "humanitarian_crisis" and state.get("active"):
            # An active UN appeal ranges from a cyclone flash appeal to famine; until severity
            # (INFORM Severity, IPC) is loaded, an active appeal alone means level 2.
            level = severity_level(country.get("humanitarian_severity"))
            drivers.append(
                {
                    "risk": risk,
                    "class": "B",
                    "level": level,
                    "active": True,
                    "severity": country.get("humanitarian_severity"),
                }
            )
            continue
        horizons = _horizons(country, adjusted, risk)
        if not horizons:
            continue
        p12 = annualised(horizons)
        level = type_level(risk, p12)
        if risk in WAR_KIND:
            # The forecast event is 25+ battle deaths a year, a minor conflict. Its probability
            # must not rank above an ongoing minor conflict, so it gives at most level 3; level
            # 4 comes from a war actually being fought (Fable round 4, #4; 1.10.0).
            level = min(level, ONSET_CAP)
        if risk in HAZARDS:
            raw = 1 + sum(1 for x in THRESHOLDS[CLASS[risk]] if p12 >= x)
            if raw > 1:
                drivers.append(
                    {
                        "risk": risk,
                        "class": CLASS[risk],
                        "level": 1,
                        "regional_level": raw,
                        "p12": round(p12, 4),
                        "regional": True,
                    }
                )
            continue
        if level > 1:
            drivers.append(
                {
                    "risk": risk,
                    "class": CLASS[risk],
                    "level": level,
                    "p12": round(p12, 4),
                    "regional": risk in HAZARDS,
                }
            )
    drivers.sort(key=lambda d: (-d["level"], d["class"], -d.get("p12", 1.0)))
    model = max([d["level"] for d in drivers], default=1)
    ministries = ministry_levels(country)
    median = lower_median(m["level"] for m in ministries)
    level = model
    raised = False
    if median is not None and median > model:
        level = min(median, model + 1)
        raised = level > model
    gap = None if median is None else median - model
    return {
        "level": level,
        "model_level": model,
        "drivers": drivers[:6],
        "ministries": ministries,
        "ministry_median": median,
        "raised_by_ministries": raised,
        "divergence": gap if gap is not None and abs(gap) >= 2 else None,
        "foreigners": foreigner_risks(country),
        "trend": trend(alert),
    }


def apply_regional(danger: dict, regional: Mapping | None) -> dict:
    """The country level is at least the level at which most of the population lives
    (regional alerts, later regional conflicts); the worst regions are named separately."""
    if not regional:
        return danger
    danger["regional"] = {
        "median": regional["level_median"],
        "max": regional["level_max"],
        "max_regions": regional["max_regions"][:6],
        "max_population_share": regional["max_population_share"],
    }
    # Until levels are computed on a population grid, first-level regions are too coarse to
    # make a whole country "extreme": fighting in part of Oromia and Amhara put all of
    # Ethiopia at 5. The regional floor lifts a country to 4 at most; regions keep their own
    # level 5 on the map (Fable round 4, 3.3; 1.10.0).
    floor = min(regional["level_median"], REGIONAL_FLOOR_CAP)
    if floor > danger["level"]:
        danger["level"] = floor
    return danger


def apply_danger(
    snapshot: Mapping,
    signals: dict,
    intensity: Mapping | None = None,
    regional: Mapping | None = None,
) -> dict:
    """Add ``danger`` to every country entry of ``signals``; returns a level histogram."""
    intensity = intensity or {}
    regional = regional or {}
    histogram = {level: 0 for level in LEVELS}
    for country in snapshot.get("countries", []):
        entry = signals["countries"].setdefault(country["iso3"], {})
        entry["danger"] = apply_regional(
            country_danger(
                country,
                entry.get("adjusted"),
                intensity.get(country["iso3"]),
                entry.get("alert"),
            ),
            regional.get(country["iso3"]),
        )
        histogram[entry["danger"]["level"]] += 1
    signals["danger_scale"] = {
        "classes": CLASS,
        "thresholds": {k: list(v) for k, v in THRESHOLDS.items()},
        "hazard_cap": HAZARD_CAP,
        "names": NAMES,
    }
    return histogram
