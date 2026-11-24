"""NOAA NCEI Global Historical Tsunami Database (HazEL API)."""

from collections import defaultdict
from collections.abc import Iterable, Mapping

from geointel.risk.countries import resolve_country_name
from geointel.risk.model import TypeHistory
from geointel.risk.taxonomy import EventType

SOURCE = "NOAA NCEI Global Historical Tsunami Database"
API = "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/tsunamis/events"
START_YEAR = 1990


def page_url(page: int) -> str:
    return f"{API}?minYear={START_YEAR}&page={page}"


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize(item: Mapping) -> dict | None:
    row = {str(k).lower(): v for k, v in item.items()}
    validity = _number(row.get("eventvalidity"))
    year = _number(row.get("year"))
    if validity is None or validity < 3 or year is None:
        return None
    country = resolve_country_name(str(row.get("country") or "").title())
    deaths = _number(row.get("deathstotal") or row.get("deaths"))
    height = _number(row.get("maxwaterheight"))
    parts = []
    if height is not None:
        parts.append(f"{height:g} m")
    if deaths:
        parts.append(f"{int(deaths)} deaths")
    month = _number(row.get("month"))
    return {
        "hazard": "TS",
        "id": f"TS-{row.get('id')}",
        "name": str(row.get("locationname") or "").title(),
        "alert": "Red" if (deaths or 0) >= 100 else "Orange",
        "year": int(year),
        "month": int(month) if month else None,
        "countries": [country] if country else [],
        "severity": ", ".join(parts),
        "lat": _number(row.get("latitude")),
        "lon": _number(row.get("longitude")),
        "deaths": deaths or 0,
    }


def normalize_all(items: Iterable[Mapping]) -> list[dict]:
    events = {}
    for item in items:
        event = normalize(item)
        if event:
            events[event["id"]] = event
    return list(events.values())


def history(events: list[dict], reference_year: int) -> TypeHistory:
    end_year = reference_year - 1
    data: dict[str, set[int]] = defaultdict(set)
    records = unresolved = 0
    for event in events:
        if not START_YEAR <= event["year"] <= end_year:
            continue
        records += 1
        if not event["countries"]:
            unresolved += 1
        for code in event["countries"]:
            data[code].add(event["year"])
    return TypeHistory(
        event_type=EventType.TSUNAMI,
        source=SOURCE,
        start_year=START_YEAR,
        end_year=end_year,
        years_with_event={k: frozenset(v) for k, v in data.items()},
        half_life_years=None,
        unresolved_labels=unresolved,
        records=records,
    )
