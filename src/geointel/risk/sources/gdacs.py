"""GDACS (UN OCHA / European Commission JRC) multi-hazard alerts.

Only Orange and Red alerts are used: GDACS sets these when an event is likely to need
international humanitarian assistance, combining physical severity, exposed population and
vulnerability. Each affected country counts the event.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping

from geointel.risk.countries import resolve_country_name, universe_codes
from geointel.risk.model import TypeHistory
from geointel.risk.taxonomy import EventType

SOURCE = "GDACS — Global Disaster Alert and Coordination System"
HAZARDS = {
    "TC": EventType.TROPICAL_CYCLONE,
    "FL": EventType.FLOOD,
    "VO": EventType.VOLCANO,
    "DR": EventType.DROUGHT,
    "WF": EventType.WILDFIRE,
}
FIRST_YEAR = {"TC": 2003, "FL": 2003, "VO": 2003, "DR": 2003, "WF": 2016}
API = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"


def page_url(hazard: str, year: int, page: int) -> str:
    return (
        f"{API}?eventlist={hazard}&fromdate={year}-01-01&todate={year}-12-31"
        f"&alertlevel=orange;red&pagesize=100&pagenumber={page}"
    )


def _lower(mapping: Mapping) -> dict:
    return {str(k).lower(): v for k, v in mapping.items()}


def normalize(feature: Mapping) -> dict | None:
    """Flatten one GeoJSON feature into a compact event record."""
    props = _lower(feature.get("properties") or {})
    hazard = str(props.get("eventtype", "")).upper()
    if hazard not in HAZARDS:
        return None
    alert = str(props.get("alertlevel", "")).capitalize()
    if alert not in ("Orange", "Red"):
        return None
    date = str(props.get("fromdate") or "")
    try:
        year, month = int(date[:4]), int(date[5:7])
    except ValueError:
        return None
    countries = set()
    for item in props.get("affectedcountries") or []:
        item = _lower(item)
        code = str(item.get("iso3") or "").upper()
        if code not in universe_codes():
            code = resolve_country_name(str(item.get("countryname") or "")) or ""
        if code:
            countries.add(code)
    if not countries:
        code = str(props.get("iso3") or "").upper()
        if code not in universe_codes():
            code = resolve_country_name(str(props.get("country") or "")) or ""
        if code:
            countries.add(code)
    coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
    severity = _lower(props.get("severitydata") or {})
    return {
        "hazard": hazard,
        "id": f"{hazard}-{props.get('eventid')}",
        "name": str(props.get("name") or props.get("eventname") or ""),
        "alert": alert,
        "year": year,
        "month": month,
        "countries": sorted(countries),
        "severity": str(severity.get("severitytext") or ""),
        "lon": coords[0] if isinstance(coords[0], int | float) else None,
        "lat": coords[1] if len(coords) > 1 and isinstance(coords[1], int | float) else None,
    }


def normalize_all(features: Iterable[Mapping]) -> list[dict]:
    """Normalize and de-duplicate (the same event can appear on several pages)."""
    seen: dict[str, dict] = {}
    for feature in features:
        event = normalize(feature)
        if event is None:
            continue
        previous = seen.get(event["id"])
        if previous is None or (previous["alert"] == "Orange" and event["alert"] == "Red"):
            seen[event["id"]] = event
    return list(seen.values())


def histories(events: list[dict], reference_year: int) -> dict[EventType, TypeHistory]:
    end_year = reference_year - 1
    result = {}
    for hazard, event_type in HAZARDS.items():
        data: dict[str, set[int]] = defaultdict(set)
        records = unresolved = 0
        for event in events:
            if event["hazard"] != hazard or event["year"] > end_year:
                continue
            if event["year"] < FIRST_YEAR[hazard]:
                continue
            records += 1
            if not event["countries"]:
                unresolved += 1
            for code in event["countries"]:
                data[code].add(event["year"])
        result[event_type] = TypeHistory(
            event_type=event_type,
            source=SOURCE,
            start_year=FIRST_YEAR[hazard],
            end_year=end_year,
            years_with_event={k: frozenset(v) for k, v in data.items()},
            half_life_years=None,
            unresolved_labels=unresolved,
            records=records,
        )
    return result
