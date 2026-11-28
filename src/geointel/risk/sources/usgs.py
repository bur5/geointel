"""USGS ComCat earthquakes of magnitude 6.5 and above."""

import csv
import io
from collections import defaultdict

from geointel.risk.countries import resolve_usgs_place
from geointel.risk.model import TypeHistory
from geointel.risk.taxonomy import EventType

SOURCE = "USGS ANSS Comprehensive Catalog"
MIN_MAGNITUDE = 6.5


def query_url(start_year: int = 1990) -> str:
    return (
        "https://earthquake.usgs.gov/fdsnws/event/1/query?format=csv"
        f"&starttime={start_year}-01-01&minmagnitude={MIN_MAGNITUDE}"
        "&eventtype=earthquake&orderby=time-asc&limit=20000"
    )


def parse(text: str, reference_year: int, start_year: int = 1990) -> TypeHistory:
    data: dict[str, set[int]] = defaultdict(set)
    unresolved = rows = 0
    end_year = reference_year - 1
    for row in csv.DictReader(io.StringIO(text)):
        try:
            year = int(row["time"][:4])
            magnitude = float(row["mag"])
        except (KeyError, ValueError):
            continue
        if year < start_year or year > end_year or magnitude < MIN_MAGNITUDE:
            continue
        if row.get("type", "earthquake") != "earthquake":
            continue
        rows += 1
        code = resolve_usgs_place(row.get("place", ""))
        if code:
            data[code].add(year)
        else:
            unresolved += 1
    return TypeHistory(
        event_type=EventType.MAJOR_EARTHQUAKE,
        source=SOURCE,
        start_year=start_year,
        end_year=end_year,
        years_with_event={k: frozenset(v) for k, v in data.items()},
        half_life_years=None,  # seismic hazard is stable on these timescales
        unresolved_labels=unresolved,
        records=rows,
    )


def events(text: str, start_year: int = 1990) -> list[dict]:
    """Located M6.5+ earthquakes for hotspot maps."""
    result = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            year = int(row["time"][:4])
            month = int(row["time"][5:7])
            magnitude = float(row["mag"])
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (KeyError, ValueError):
            continue
        if year < start_year or magnitude < MIN_MAGNITUDE:
            continue
        code = resolve_usgs_place(row.get("place", ""))
        result.append(
            {
                "hazard": "EQ",
                "id": f"EQ-{row.get('id')}",
                "source": "usgs",
                "name": row.get("place", ""),
                "alert": "Red" if magnitude >= 7.5 else "Orange",
                "year": year,
                "month": month,
                "countries": [code] if code else [],
                "severity": f"M{magnitude:.1f}",
                "magnitude": magnitude,
                "lat": lat,
                "lon": lon,
            }
        )
    return result
