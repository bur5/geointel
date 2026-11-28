"""UCDP Georeferenced Event Dataset (annual) and UCDP Candidate events (monthly): where
fighting and attacks with deaths happen, aggregated to 0.1° cells for the regional layer.

Licence: UCDP data are free to use with citation (Sundberg & Melander 2013; Davies et al.).
"""

import csv
import io
import re
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date

from geointel.risk.countries import resolve_country_name

DOWNLOADS = "https://ucdp.uu.se/downloads/"
SOURCE = "UCDP GED and UCDP Candidate Events"
YEARS_KEPT = 3


def links(html: str) -> dict[str, str | None]:
    """Newest annual GED CSV, the cumulative Candidate file and the latest monthly one."""
    hrefs = re.findall(r'href="([^"]+)"', html)
    ged = sorted(
        (h for h in hrefs if re.search(r"/ged/ged(\d+)-csv\.zip$", h)),
        key=lambda h: int(re.search(r"ged(\d+)-csv", h).group(1)),
    )
    cumulative = [h for h in hrefs if re.search(r"GEDEvent_v\d+_01_\d+_\d+\.csv$", h)]
    monthly = sorted(
        (h for h in hrefs if re.search(r"GEDEvent_v\d+_0_\d+\.csv$", h, re.I)),
        key=lambda h: [int(x) for x in re.findall(r"\d+", h.rsplit("/", 1)[-1])],
    )
    return {
        "ged": ged[-1] if ged else None,
        "candidate_cumulative": cumulative[-1] if cumulative else None,
        "candidate_latest": monthly[-1] if monthly else None,
    }


CELLS_VERSION = 2  # cells carry the UCDP type of violence (1.10.0)
STATE_BASED = 1  # 1 state-based, 2 non-state (e.g. cartels fighting each other), 3 one-sided


def cells(text: str, min_year: int, seen: set | None = None) -> list[dict]:
    """Deaths by country, 0.1° cell, month and UCDP type of violence (events from
    ``min_year`` on). ``seen`` collects event ids so that an event present in two files
    (the cumulative and the latest Candidate release) is counted once."""
    acc: dict[tuple, float] = defaultdict(float)
    for row in csv.DictReader(io.StringIO(text)):
        try:
            year = int(row.get("year") or str(row.get("date_start", ""))[:4])
            lat, lon = float(row["latitude"]), float(row["longitude"])
            deaths = float(row.get("best") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if year < min_year:
            continue
        event_id = str(row.get("id") or "").strip()
        if seen is not None and event_id:
            if event_id in seen:
                continue
            seen.add(event_id)
        month = str(row.get("date_start") or "")[:7] or f"{year}-01"
        code = resolve_country_name(str(row.get("country") or ""))
        if not code:
            continue
        try:
            kind = int(row.get("type_of_violence") or STATE_BASED)
        except ValueError:
            kind = STATE_BASED
        acc[(code, round(lat, 1), round(lon, 1), month, kind)] += deaths
    return [
        {"iso3": c, "lat": la, "lon": lo, "month": m, "type": k, "deaths": round(d, 1)}
        for (c, la, lo, m, k), d in acc.items()
    ]


def read_zip_csv(payload: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        return archive.read(name).decode("utf-8-sig")


def _per100k(deaths: float, population: int | None) -> float | None:
    return deaths * 100_000 / population if population else None


def _at_least(rate: float | None, threshold: float) -> bool:
    """Per-capita condition; without population data only the absolute count decides."""
    return rate is None or rate >= threshold


def conflict_level(
    state_90d: float,
    state_12m: float,
    other_90d: float,
    other_12m: float,
    population: int | None,
) -> int:
    """Region level from deaths (1.12.0, Fable round 4, 3.2).

    State-based fighting (UCDP type 1): 5 = 250+ deaths in 90 days and 2+ per 100,000 in
    90 days; 4 = 50+ in 90 days and 0.5+ per 100,000, or 150+ in 12 months and 2+ per
    100,000. Violence between armed groups (type 2, e.g. cartels) and against civilians
    (type 3) stops at 4, and reaches 4 only at 10+ deaths per 100,000 a year (and 150+).
    All types together: 3 = 25+ in 12 months, 2 = 5+ in 12 months.
    """

    def rate(deaths: float) -> float | None:
        return _per100k(deaths, population)

    level = 0
    if state_90d >= 250 and _at_least(rate(state_90d), 2.0):
        level = 5
    elif (state_90d >= 50 and _at_least(rate(state_90d), 0.5)) or (
        state_12m >= 150 and _at_least(rate(state_12m), 2.0)
    ):
        level = 4
    if level < 4 and other_12m >= 150 and _at_least(rate(other_12m), 10.0):
        level = 4
    total_12m = state_12m + other_12m
    if level < 3 and total_12m >= 25:
        level = 3
    if level < 2 and total_12m >= 5:
        level = 2
    return level


def region_levels(
    items: Iterable[Mapping],
    locate,
    today: date,
    population: Mapping[str, Mapping[str, int]] | None = None,
) -> dict[str, dict[str, dict]]:
    """iso3 -> region code -> level with a reason, deaths and the 0.25° cells with deaths.

    ``population``: iso3 -> region code -> people (population grid); without it the
    per-capita conditions are skipped.
    """
    from geointel.risk.popgrid import cell_of

    acc: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"s90": 0.0, "s12": 0.0, "o90": 0.0, "o12": 0.0}
    )
    hot: dict[tuple[str, str], set] = defaultdict(set)
    for item in items:
        y, m = int(item["month"][:4]), int(item["month"][5:7])
        # Months back from the current one: 0..11 is twelve months, 0..2 three months
        # (the windows were one month too long before 1.10.0, Fable round 4 #6).
        age = (today.year - y) * 12 + today.month - m
        if age >= 12 or age < 0:
            continue
        found = locate(item["iso3"], item["lat"], item["lon"])
        if not found:
            continue
        key = (item["iso3"], found[2])
        state = int(item.get("type", STATE_BASED)) == STATE_BASED
        deaths = float(item["deaths"])
        a = acc[key]
        a["s12" if state else "o12"] += deaths
        if age < 3:
            a["s90" if state else "o90"] += deaths
        if deaths > 0:
            hot[key].add(cell_of(item["lat"], item["lon"]))
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for key, a in acc.items():
        pop = ((population or {}).get(key[0]) or {}).get(key[1]) or None
        level = conflict_level(a["s90"], a["s12"], a["o90"], a["o12"], pop)
        if not level:
            continue
        r = a["s90"] + a["o90"]
        deaths = a["s12"] + a["o12"]
        armed_groups = a["o12"] > a["s12"]
        what_ru = (
            "погибших в насилии вооружённых групп и нападениях на мирных жителей"
            if armed_groups
            else "погибших в боях и нападениях"
        )
        what_en = (
            "deaths in violence by armed groups and attacks on civilians"
            if armed_groups
            else "deaths in fighting and attacks"
        )
        rate_ru = rate_en = ""
        if pop:
            per = round(deaths * 100_000 / pop, 1)
            rate_ru = f", {per} на 100 тыс. жителей за год"
            rate_en = f", {per} per 100,000 people a year"
        out[key[0]][key[1]] = {
            "level": level,
            "deaths_90d": round(r),
            "deaths_12m": round(deaths),
            "state_based_12m": round(a["s12"]),
            "armed_groups": armed_groups,
            "hot_cells": sorted(hot[key]),
            "reason_ru": f"{what_ru}: {round(r)} за 3 месяца, {round(deaths)} за 12 месяцев"
            f"{rate_ru} (UCDP)",
            "reason_en": f"{what_en}: {round(r)} in 3 months, {round(deaths)} in 12 months"
            f"{rate_en} (UCDP)",
        }
    return dict(out)


def country_year(text: str, min_year: int = 1989) -> dict[str, dict[int, tuple[float, float]]]:
    """ISO3 -> year -> (deaths in state-based fighting, deaths in other violence: non-state
    and one-sided), from the annual GED file. Used by the time machine (experiment B)."""
    acc: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for row in csv.DictReader(io.StringIO(text)):
        try:
            year = int(row.get("year") or 0)
            deaths = float(row.get("best") or 0)
            kind = int(row.get("type_of_violence") or STATE_BASED)
        except (TypeError, ValueError):
            continue
        if year < min_year:
            continue
        code = resolve_country_name(str(row.get("country") or ""))
        if not code:
            continue
        acc[code][year][0 if kind == STATE_BASED else 1] += deaths
    return {c: {y: (v[0], v[1]) for y, v in years.items()} for c, years in acc.items()}
