"""Assemble the public risk snapshot JSON and the changes since the previous snapshot."""

from collections.abc import Mapping
from datetime import UTC, datetime

from geointel.risk.countries import universe
from geointel.risk.model import METHOD_NAME, TypeHistory, assess_type
from geointel.risk.taxonomy import EVENT_TYPES, HORIZONS, EventType

SCHEMA = "geointel-risk-snapshot-v1"


def coup_groups(history: TypeHistory, regimes: dict) -> dict[str, str]:
    """Group countries by V-Dem Regimes of the World (0 closed autocracy … 3 liberal
    democracy) and whether coups or attempts happened in 2+ of the last 20 years."""
    recent_from = history.end_year - 19
    groups = {}
    for iso3, item in regimes.items():
        regime = int(round(float(item["value"])))
        # Two or more coup years in 20 years: one disputed episode (the Cline Center codes
        # 6 January 2021 as an attempt) must not move a stable democracy into the coup group;
        # the episode stays in the country's own history (Fable round 4, #3; 1.10.0).
        recent = sum(1 for y in history.years_with_event.get(iso3, ()) if y >= recent_from) >= 2
        groups[iso3] = f"{regime}|{'coup20' if recent else 'none20'}"
    return groups


TEN_YEAR_SHOWN = frozenset(
    {
        EventType.MAJOR_EARTHQUAKE,
        EventType.TSUNAMI,
        EventType.VOLCANO,
        EventType.TROPICAL_CYCLONE,
        EventType.FLOOD,
        EventType.DROUGHT,
        EventType.WILDFIRE,
    }
)
COUP_WORLD_CAP = 2.0
DEMOCRACY_GROUPS = frozenset({"2|none20", "3|none20"})

CHANGE_THRESHOLD = 0.02

METHOD = {
    "name": METHOD_NAME,
    "calibration": "not_calibrated",
    "interval": "90% posterior interval",
    "description_en": (
        "Historical base rates since 1990 per country, shrunk towards the global "
        "distribution (empirical Bayes) and weighted towards recent years. Armed conflicts "
        "use a two-state model: for ongoing conflicts the probability that the conflict is "
        "still active at the end of the horizon, otherwise the probability of onset. This is "
        "an outside-view baseline without current-news adjustment and is not yet calibrated."
    ),
    "description_ru": (
        "Исторические частоты с 1990 года по каждой стране, сглаженные к мировому "
        "распределению (эмпирический Байес) с повышенным весом последних лет. Для "
        "вооружённых конфликтов — модель двух состояний: для идущего конфликта это "
        "вероятность, что он ещё будет активен в конце горизонта, иначе — вероятность "
        "начала. Это базовая оценка «внешнего взгляда» без учёта текущих новостей; "
        "калибровка ещё не проводилась."
    ),
}


def _round(value: float) -> float:
    return round(value, 4)


# Types whose per-country probability is not better than a simple rule on the time machine
# (coups +0.02, economic crisis about 0): the site shows a group, "background" or "elevated"
# (2× the world average or more), instead of a percentage (Fable round 5, 3.6.8; 1.17.0).
GROUP_DISPLAY = ("coup_attempt", "economic_crisis")
ELEVATED_RATIO = 2.0


def mark_grouped(snapshot: dict, keys: tuple[str, ...] = GROUP_DISPLAY) -> None:
    for key in keys:
        rows = [
            r
            for c in snapshot["countries"]
            if (r := c["risks"].get(key)) and r.get("question") == "onset_within"
        ]
        values = [r["horizons"]["1y"]["p"] for r in rows if r["horizons"].get("1y")]
        if not values:
            continue
        mean = sum(values) / len(values)
        for r in rows:
            p = r["horizons"]["1y"]["p"]
            ratio = p / mean if mean else 1.0
            r["display"] = {
                "mode": "group",
                "group": "elevated" if ratio >= ELEVATED_RATIO else "background",
                "ratio": round(ratio, 1),
            }


# Interstate war: the per-country onset probability was not better than the world rate on
# the time machine, and experiment C (rivalries) did not pass (docs/backtest-rules.md). By
# the owner's decision recorded before the run, the site shows only whether such a war is
# going on, the preparation signs and one sentence on the world rate (1.17.0).
STATUS_ONLY = ("interstate_conflict",)


def mark_status(snapshot: dict, keys: tuple[str, ...] = STATUS_ONLY) -> None:
    for key in keys:
        for c in snapshot["countries"]:
            r = c["risks"].get(key)
            if r and r.get("question") == "onset_within":
                r["display"] = {"mode": "status"}
                r["hidden_horizons"] = ["1m", "1y", "5y", "10y"]


def build_snapshot(
    histories: Mapping[EventType, TypeHistory | None],
    sources: list[dict],
    generated_at: datetime | None = None,
    previous: dict | None = None,
    extras: dict | None = None,
) -> dict:
    generated_at = generated_at or datetime.now(UTC)
    countries = universe()
    first_years = {c.iso3: c.first_year for c in countries}
    risks: dict[str, dict] = {c.iso3: {} for c in countries}
    type_entries = []
    for spec in EVENT_TYPES:
        history = histories.get(spec.key)
        entry = {
            "key": spec.key.value,
            "label_en": spec.label_en,
            "label_ru": spec.label_ru,
            "resolution_en": spec.resolution_en,
            "resolution_ru": spec.resolution_ru,
            "modeled": spec.modeled,
            "group": spec.group,
            "available": history is not None,
        }
        if history is not None:
            entry.update(
                source=history.source,
                data_window=[history.start_year, history.end_year],
                records=history.records,
                unresolved_labels=history.unresolved_labels,
            )
            groups = None
            world_cap = None
            # 10-year forecasts are shown only for natural hazards, whose yearly rate is
            # stable over decades; for political events a one-year rate extended over ten
            # years has never been checked (Fable round 5, 3.6.7; 1.17.0).
            hidden: list[str] = [] if spec.key in TEN_YEAR_SHOWN else ["10y"]
            if hidden:
                entry["hidden_horizons"] = hidden
            if spec.key == EventType.COUP_ATTEMPT:
                # Chosen on the time machine's tuning period (docs/backtest-rules.md, run 4):
                # democracies without coups are pooled with each other, every other country
                # with the world, and the prior weighs at most twice a country's own record.
                # 10-year coup forecasts cannot be checked and are not shown (1.11.0).
                world_cap = COUP_WORLD_CAP
                if (extras or {}).get("regimes"):
                    groups = {
                        c: g
                        for c, g in coup_groups(history, extras["regimes"]).items()
                        if g in DEMOCRACY_GROUPS
                    }
                    entry["grouping"] = "democracies without coups pooled; others: world"
            for item in assess_type(history, first_years, spec.persistent_state, groups, world_cap):
                risks[item.iso3][spec.key.value] = {
                    "question": item.question.value,
                    "active": item.active,
                    "state_as_of": item.state_as_of,
                    "confidence": item.confidence,
                    "horizons": {
                        key: {"p": _round(v.p), "low": _round(v.low), "high": _round(v.high)}
                        for key, v in item.horizons.items()
                    },
                    "basis": {
                        "exposure_years": item.exposure_years,
                        "event_years": item.event_years,
                        "last_event_year": item.last_event_year,
                    },
                }
                if hidden:
                    risks[item.iso3][spec.key.value]["hidden_horizons"] = hidden
        type_entries.append(entry)

    snapshot = {
        "schema": SCHEMA,
        "generated_at": generated_at.isoformat(),
        "method": METHOD,
        "horizons": [
            {"key": h.key, "years": h.years, "label_en": h.label_en, "label_ru": h.label_ru}
            for h in HORIZONS
        ],
        "event_types": type_entries,
        "sources": sources,
        "countries": [
            {
                "iso3": c.iso3,
                "iso2": c.iso2,
                "numeric": c.numeric,
                "name": c.name,
                "risks": risks[c.iso3],
                "advisory": (extras or {}).get("advisories", {}).get(c.iso3),
                "advisory_uk": (extras or {}).get("fcdo", {}).get(c.iso3),
                "advisories": (extras or {}).get("ministries", {}).get(c.iso3),
                "humanitarian_severity": (extras or {}).get("severity", {}).get(c.iso3),
                "profile": (extras or {}).get("profiles", {}).get(c.iso3),
                "outlook": (extras or {}).get("outlook", {}).get(c.iso3),
                "democracy": (extras or {}).get("democracy", {}).get(c.iso3),
                "gpr": (extras or {}).get("gpr", {}).get(c.iso3),
                "elections": (extras or {}).get("elections", {}).get(c.iso3, []),
            }
            for c in countries
        ],
    }
    mark_grouped(snapshot)
    mark_status(snapshot)
    snapshot["changes"] = diff_snapshots(previous, snapshot) if previous else []
    snapshot["previous_generated_at"] = previous.get("generated_at") if previous else None
    return snapshot


def diff_snapshots(previous: dict, current: dict, threshold: float = CHANGE_THRESHOLD) -> list:
    """Probability moves of at least ``threshold`` and question/state flips."""
    before = {c["iso3"]: c["risks"] for c in previous.get("countries", [])}
    changes = []
    for country in current["countries"]:
        old_risks = before.get(country["iso3"], {})
        for event_type, risk in country["risks"].items():
            old = old_risks.get(event_type)
            if old is None:
                continue
            if old.get("question") != risk["question"]:
                changes.append(
                    {
                        "iso3": country["iso3"],
                        "event_type": event_type,
                        "kind": "state_change",
                        "from": old.get("question"),
                        "to": risk["question"],
                    }
                )
                continue
            for horizon, value in risk["horizons"].items():
                if horizon in risk.get("hidden_horizons", ()):
                    continue
                previous_p = old.get("horizons", {}).get(horizon, {}).get("p")
                if previous_p is None:
                    continue
                delta = value["p"] - previous_p
                if abs(delta) >= threshold:
                    changes.append(
                        {
                            "iso3": country["iso3"],
                            "event_type": event_type,
                            "kind": "probability_change",
                            "horizon": horizon,
                            "from": previous_p,
                            "to": value["p"],
                            "delta": _round(delta),
                        }
                    )
    changes.sort(key=lambda c: -abs(c.get("delta", 1.0)))
    return changes
