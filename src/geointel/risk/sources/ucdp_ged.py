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


def region_levels(items: Iterable[Mapping], locate, today: date) -> dict[str, dict[str, dict]]:
    """iso3 -> region code -> level with a reason.

    5: 250+ deaths in the last 90 days (a war zone now); 4: 50+ in 90 days or 150+ in
    12 months; 3: 25+ in 12 months; 2: 5+ in 12 months. The 1.6.0 rule (5+ deaths in 90 days
    → 5) put ordinary criminal-violence regions at the top level (1.9.0).
    """
    recent: dict[tuple[str, str], float] = defaultdict(float)
    year: dict[tuple[str, str], float] = defaultdict(float)
    state_recent: dict[tuple[str, str], float] = defaultdict(float)
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
        year[key] += item["deaths"]
        if age < 3:
            recent[key] += item["deaths"]
            if int(item.get("type", STATE_BASED)) == STATE_BASED:
                state_recent[key] += item["deaths"]
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for key, deaths in year.items():
        r = recent.get(key, 0.0)
        # Level 5 ("war zone") only from fighting that involves a state; violence between
        # armed groups (cartels) or attacks on civilians alone stop at 4 (Fable round 4, #8).
        level = (
            5
            if state_recent.get(key, 0.0) >= 250
            else 4
            if r >= 50 or deaths >= 150 or r >= 250
            else 3
            if deaths >= 25
            else 2
            if deaths >= 5
            else 0
        )
        if not level:
            continue
        out[key[0]][key[1]] = {
            "level": level,
            "deaths_90d": round(r),
            "deaths_12m": round(deaths),
            "reason_ru": f"погибших в боях и нападениях: {round(r)} за 3 месяца, "
            f"{round(deaths)} за 12 месяцев (UCDP)",
            "reason_en": f"deaths in fighting and attacks: {round(r)} in 3 months, "
            f"{round(deaths)} in 12 months (UCDP)",
        }
    return dict(out)
