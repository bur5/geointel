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


def cells(text: str, min_year: int) -> list[dict]:
    """Deaths by country, 0.1° cell and month (events from ``min_year`` on)."""
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
        month = str(row.get("date_start") or "")[:7] or f"{year}-01"
        code = resolve_country_name(str(row.get("country") or ""))
        if not code:
            continue
        acc[(code, round(lat, 1), round(lon, 1), month)] += deaths
    return [
        {"iso3": c, "lat": la, "lon": lo, "month": m, "deaths": round(d, 1)}
        for (c, la, lo, m), d in acc.items()
    ]


def read_zip_csv(payload: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        return archive.read(name).decode("utf-8-sig")


def region_levels(items: Iterable[Mapping], locate, today: date) -> dict[str, dict[str, dict]]:
    """iso3 -> region code -> level with a reason.

    5: 5+ deaths in the last 90 days (fighting or attacks now); 4: 25+ deaths in the last
    12 months; 3: 5+ deaths in the last 12 months.
    """
    recent: dict[tuple[str, str], float] = defaultdict(float)
    year: dict[tuple[str, str], float] = defaultdict(float)
    for item in items:
        y, m = int(item["month"][:4]), int(item["month"][5:7])
        age = (today.year - y) * 12 + today.month - m
        if age > 12 or age < 0:
            continue
        found = locate(item["iso3"], item["lat"], item["lon"])
        if not found:
            continue
        key = (item["iso3"], found[2])
        year[key] += item["deaths"]
        if age <= 3:
            recent[key] += item["deaths"]
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for key, deaths in year.items():
        r = recent.get(key, 0.0)
        level = 5 if r >= 5 else 4 if deaths >= 25 else 3 if deaths >= 5 else 0
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
