"""Mass Mobilization (Clark & Regan, Harvard Dataverse, CC0): protests against governments.

A country-year counts as a mass protest year if at least one protest against the government
had more than 10,000 participants. The dataset ends in 2020, so GeoIntel's protest base
rates describe 1990–2020 and are labelled as such; current months are covered by news signs.
Countries absent from the dataset are reported as "no data", never as zero.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping

from geointel.risk.countries import resolve_country_name

SOURCE = "Mass Mobilization (Clark & Regan), protests of 10,000+ people, 1990–2020"
DATASET = (
    "https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId=doi:10.7910/DVN/HTTWYL"
)
FILE = "https://dataverse.harvard.edu/api/access/datafile/{id}?format=original"
START_YEAR = 1990


def pick_file(meta: Mapping) -> dict | None:
    files = (meta.get("data") or {}).get("latestVersion", {}).get("files") or []
    for f in files:
        name = str((f.get("dataFile") or {}).get("filename") or "").lower()
        if name.endswith((".tab", ".csv")) and "mm" in name:
            return f["dataFile"]
    return None


def parse(text: str) -> dict:
    """{"last": year, "covered": [ISO3], "years": {ISO3: [years with a 10,000+ protest]}}."""
    years: dict[str, set[int]] = {}
    covered: set[str] = set()
    last = 0
    reader = csv.DictReader(io.StringIO(text), delimiter="\t" if "\t" in text[:500] else ",")
    for row in reader:
        try:
            year = int(row.get("year") or 0)
        except ValueError:
            continue
        code = resolve_country_name(str(row.get("country") or ""))
        if not code or not year:
            continue
        last = max(last, year)
        covered.add(code)
        if str(row.get("protest", "1")) != "1":
            continue
        if str(row.get("participants_category") or "").strip() != ">10000":
            continue
        years.setdefault(code, set()).add(year)
    return {
        "last": last,
        "covered": sorted(covered),
        "years": {k: sorted(v) for k, v in sorted(years.items())},
    }


def history(payload: Mapping):
    from geointel.risk.model import TypeHistory
    from geointel.risk.taxonomy import EventType

    last = int(payload["last"])
    span = frozenset(range(START_YEAR, last + 1))
    return TypeHistory(
        EventType.MASS_PROTEST,
        SOURCE,
        START_YEAR,
        last,
        {k: frozenset(v) for k, v in payload["years"].items()},
        observed_years={code: span for code in payload["covered"]},
        metadata={"data_ends": last},
    )
