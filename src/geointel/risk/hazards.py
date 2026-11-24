"""Per-country natural-hazard details: where events happened, how severe, which months."""

from collections import defaultdict
from datetime import UTC, datetime

from geointel.risk.countries import universe_codes

HAZARD_TYPES = {
    "EQ": "major_earthquake",
    "TS": "tsunami",
    "TC": "tropical_cyclone",
    "FL": "flood",
    "VO": "volcano",
    "DR": "drought",
    "WF": "wildfire",
}
MAX_EVENTS_PER_HAZARD = 12


def _rank(event: dict) -> tuple:
    return (
        event.get("alert") == "Red",
        event.get("magnitude") or event.get("deaths") or 0,
        event.get("year") or 0,
    )


def build_hazard_details(events: list[dict], generated_at: datetime | None = None) -> dict:
    by_country: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for event in events:
        for code in event.get("countries") or []:
            if code in universe_codes():
                by_country[code][event["hazard"]].append(event)
    countries = {}
    for code, hazards in by_country.items():
        entry: dict[str, dict] = {}
        for hazard, items in hazards.items():
            months = [0] * 12
            for item in items:
                if item.get("month"):
                    months[int(item["month"]) - 1] += 1
            top = sorted(items, key=_rank, reverse=True)[:MAX_EVENTS_PER_HAZARD]
            region_counts: dict[tuple[str, str], int] = defaultdict(int)
            for item in items:
                if item.get("region_en"):
                    region_counts[
                        (item["region_en"], item.get("region_ru") or item["region_en"])
                    ] += 1
            entry[HAZARD_TYPES[hazard]] = {
                "count": len(items),
                "red": sum(1 for item in items if item.get("alert") == "Red"),
                "first_year": min(item["year"] for item in items),
                "last_year": max(item["year"] for item in items),
                "months": months,
                "regions": [
                    {"en": en, "ru": ru, "n": n}
                    for (en, ru), n in sorted(region_counts.items(), key=lambda kv: -kv[1])[:8]
                ],
                "events": [
                    {
                        "name": item.get("name", ""),
                        "alert": item.get("alert"),
                        "year": item.get("year"),
                        "month": item.get("month"),
                        "severity": item.get("severity", ""),
                        "region_en": item.get("region_en"),
                        "region_ru": item.get("region_ru"),
                        "lat": round(item["lat"], 2) if item.get("lat") is not None else None,
                        "lon": round(item["lon"], 2) if item.get("lon") is not None else None,
                    }
                    for item in top
                ],
            }
        countries[code] = entry
    return {
        "schema": "geointel-hazard-details-v1",
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
        "countries": countries,
    }
