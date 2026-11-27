"""UCDP/PRIO Armed Conflict Dataset (country-year occurrence of armed conflict)."""

import csv
import io
import zipfile
from collections import defaultdict

from geointel.risk.countries import resolve_country_name
from geointel.risk.model import TypeHistory
from geointel.risk.taxonomy import EventType

SOURCE = "UCDP/PRIO Armed Conflict Dataset"
INTERNAL_TYPES = {"3", "4"}
INTERSTATE_TYPE = "2"
# UCDP codes the US campaign against al-Qaida (2001 onwards) as an intrastate conflict located
# in the USA, although the fighting took place abroad. Counting it as internal war on US soil
# gave the USA a 10% yearly onset risk. Until geocoded events (UCDP GED) decide where fighting
# happens, these countries' "internal" years are taken only from type-3 conflicts.
TRANSNATIONAL_GOVERNMENTS = frozenset({"USA"})


def read_csv_bytes(payload: bytes) -> str:
    """Accept either the zipped download or a plain CSV."""
    if payload[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
            return archive.read(name).decode("utf-8-sig")
    return payload.decode("utf-8-sig")


def _split(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def parse(
    text: str, start_year: int = 1990, version: str | None = None
) -> tuple[TypeHistory, TypeHistory]:
    internal: dict[str, set[int]] = defaultdict(set)
    interstate: dict[str, set[int]] = defaultdict(set)
    unresolved_internal = unresolved_interstate = 0
    rows = 0
    max_year = start_year
    for row in csv.DictReader(io.StringIO(text)):
        year = int(row["year"])
        max_year = max(max_year, year)
        if year < start_year:
            continue
        rows += 1
        kind = str(row.get("type_of_conflict", "")).strip()
        if kind in INTERNAL_TYPES:
            for label in _split(row.get("location", "")):
                code = resolve_country_name(label)
                if code in TRANSNATIONAL_GOVERNMENTS and kind != "3":
                    continue
                if code:
                    internal[code].add(year)
                else:
                    unresolved_internal += 1
        elif kind == INTERSTATE_TYPE:
            for label in _split(row.get("side_a", "")) + _split(row.get("side_b", "")):
                code = resolve_country_name(label)
                if code:
                    interstate[code].add(year)
                else:
                    unresolved_interstate += 1
    meta = {"dataset_version": version} if version else {}

    def history(kind: EventType, data: dict[str, set[int]], unresolved: int) -> TypeHistory:
        return TypeHistory(
            event_type=kind,
            source=SOURCE,
            start_year=start_year,
            end_year=max_year,
            years_with_event={k: frozenset(v) for k, v in data.items()},
            half_life_years=10.0,
            unresolved_labels=unresolved,
            records=rows,
            metadata=meta,
        )

    return (
        history(EventType.INTERNAL_ARMED_CONFLICT, internal, unresolved_internal),
        history(EventType.INTERSTATE_CONFLICT, interstate, unresolved_interstate),
    )


def dyad_years(text: str, start_year: int = 1946) -> dict[frozenset[str], set[int]]:
    """Interstate conflict years per pair of opposing states (side A vs side B)."""
    result: dict[frozenset[str], set[int]] = defaultdict(set)
    for row in csv.DictReader(io.StringIO(text)):
        if str(row.get("type_of_conflict", "")).strip() != INTERSTATE_TYPE:
            continue
        year = int(row["year"])
        if year < start_year:
            continue
        side_a = [c for c in map(resolve_country_name, _split(row.get("side_a", ""))) if c]
        side_b = [c for c in map(resolve_country_name, _split(row.get("side_b", ""))) if c]
        for a in side_a:
            for b in side_b:
                if a != b:
                    result[frozenset((a, b))].add(year)
    return dict(result)


def latest_intensity(text: str) -> dict[str, dict[str, int]]:
    """Highest UCDP intensity (1 = 25–999 battle deaths, 2 = war, 1,000+) in the latest year,
    per country, separately for internal and interstate conflicts."""
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return {}
    last = max(int(r["year"]) for r in rows)
    result: dict[str, dict[str, int]] = defaultdict(dict)
    for row in rows:
        if int(row["year"]) != last:
            continue
        kind = str(row.get("type_of_conflict", "")).strip()
        try:
            level = int(row.get("intensity_level") or 0)
        except ValueError:
            continue
        if kind in INTERNAL_TYPES:
            labels, key = _split(row.get("location", "")), "internal"
        elif kind == INTERSTATE_TYPE:
            labels = _split(row.get("side_a", "")) + _split(row.get("side_b", ""))
            key = "interstate"
        else:
            continue
        for label in labels:
            code = resolve_country_name(label)
            if code:
                result[code][key] = max(result[code].get(key, 0), level)
    return dict(result)
