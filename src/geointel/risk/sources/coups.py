"""Powell & Thyne global instances of coups (attempted and successful)."""

import csv
import io
from collections import defaultdict

from geointel.risk.countries import resolve_country_name
from geointel.risk.model import TypeHistory
from geointel.risk.taxonomy import EventType

SOURCE = "Powell & Thyne Global Instances of Coups"


def parse(text: str, reference_year: int, start_year: int = 1990) -> TypeHistory:
    """Count coup years through ``reference_year - 1`` (the last complete year)."""
    dialect = "excel-tab" if "\t" in text.splitlines()[0] else "excel"
    data: dict[str, set[int]] = defaultdict(set)
    unresolved = rows = 0
    end_year = reference_year - 1
    for row in csv.DictReader(io.StringIO(text), dialect=dialect):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        try:
            year = int(float(row["year"]))
            outcome = int(float(row.get("coup", "0") or 0))
        except (KeyError, ValueError):
            continue
        if year < start_year or year > end_year or outcome not in (1, 2):
            continue
        rows += 1
        code = resolve_country_name(row.get("country", ""))
        if code:
            data[code].add(year)
        else:
            unresolved += 1
    return TypeHistory(
        event_type=EventType.COUP_ATTEMPT,
        source=SOURCE,
        start_year=start_year,
        end_year=end_year,
        years_with_event={k: frozenset(v) for k, v in data.items()},
        half_life_years=10.0,
        unresolved_labels=unresolved,
        records=rows,
    )
