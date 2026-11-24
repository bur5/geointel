"""Assemble the public risk snapshot JSON and the changes since the previous snapshot."""

from collections.abc import Mapping
from datetime import UTC, datetime

from geointel.risk.countries import universe
from geointel.risk.model import METHOD_NAME, TypeHistory, assess_type
from geointel.risk.taxonomy import EVENT_TYPES, HORIZONS, EventType

SCHEMA = "geointel-risk-snapshot-v1"
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
            for item in assess_type(history, first_years, spec.persistent_state):
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
                "profile": (extras or {}).get("profiles", {}).get(c.iso3),
            }
            for c in countries
        ],
    }
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
