"""GDELT event data: daily counts of protests, fighting, coercion and hostility between states.

GDELT codes news reports automatically, so the counts measure reported events, not ground
truth. Signals therefore compare a country's recent share of such events with its own past
(a z-score), which cancels most of the media-volume bias.
"""

import csv
import io
import math
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, timedelta

from geointel.risk.countries import resolve_country_name, universe_codes

SOURCE = "GDELT Event Database"
V1_DAILY = "http://data.gdeltproject.org/events/{day}.export.CSV.zip"
V2_15MIN = "http://data.gdeltproject.org/gdeltv2/{stamp}.export.CSV.zip"
BASELINE_DAYS = 180
WINDOW_DAYS = 7
MIN_BASELINE = 28

CATEGORIES = ("all", "protest", "armed", "repression", "external")
HOSTILE_ROOTS = {"13", "15", "17", "18", "19", "20"}


def v2_stamps(day: date) -> list[str]:
    base = day.strftime("%Y%m%d")
    return [f"{base}{h:02d}{m:02d}00" for h in range(24) for m in (0, 15, 30, 45)]


def _columns(n: int) -> dict[str, int] | None:
    """Column positions for GDELT 1.0 (58 columns) and 2.0 (61 columns) event exports."""
    if n >= 61:
        return {"a1": 7, "a2": 17, "root": 28, "geo_name": 52, "root_flag": 25}
    if n >= 57:
        return {"a1": 7, "a2": 17, "root": 28, "geo_name": 50, "root_flag": 25}
    return None


_place_cache: dict[str, str | None] = {}


def _place_country(full_name: str) -> str | None:
    if not full_name:
        return None
    if full_name not in _place_cache:
        _place_cache[full_name] = resolve_country_name(full_name.rsplit(",", 1)[-1].strip())
    return _place_cache[full_name]


def read_export(payload: bytes) -> str:
    if payload[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return archive.read(archive.namelist()[0]).decode("utf-8", errors="replace")
    return payload.decode("utf-8", errors="replace")


def aggregate(texts: Iterable[str], watch: set[tuple[str, str]] | None = None) -> dict:
    """Counts per country and category for one day, plus hostile counts for watched dyads."""
    universe = universe_codes()
    counts: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(CATEGORIES, 0))
    dyads: dict[str, int] = defaultdict(int)
    for text in texts:
        for row in csv.reader(io.StringIO(text), delimiter="\t"):
            cols = _columns(len(row))
            if cols is None or row[cols["root_flag"]] != "1":
                continue
            root = row[cols["root"]]
            a1, a2 = row[cols["a1"]], row[cols["a2"]]
            a1 = a1 if a1 in universe else ""
            a2 = a2 if a2 in universe else ""
            place = _place_country(row[cols["geo_name"]]) or a1
            if place:
                c = counts[place]
                c["all"] += 1
                if root == "14":
                    c["protest"] += 1
                elif root in ("18", "19", "20") and not (a1 and a2 and a1 != a2):
                    c["armed"] += 1
                elif root == "17":
                    c["repression"] += 1
            if a1 and a2 and a1 != a2 and root in HOSTILE_ROOTS:
                for code in (a1, a2):
                    if code != place:
                        counts[code]["all"] += 1
                    counts[code]["external"] += 1
                if watch is None or (a1, a2) in watch:
                    dyads[f"{a1}>{a2}"] += 1
    return {"countries": {k: dict(v) for k, v in counts.items()}, "dyads": dict(dyads)}


def merge_days(cache: Mapping[str, dict], new: Mapping[str, dict], today: date) -> dict:
    keep_from = (today - timedelta(days=BASELINE_DAYS + WINDOW_DAYS + 2)).isoformat()
    merged = {d: v for d, v in {**cache, **new}.items() if d >= keep_from}
    return dict(sorted(merged.items()))


def missing_days(cache: Mapping[str, dict], today: date, limit: int) -> list[date]:
    """Yesterday first, then backfill towards the start of the baseline window."""
    wanted = [today - timedelta(days=i) for i in range(1, BASELINE_DAYS + WINDOW_DAYS + 1)]
    return [d for d in wanted if d.isoformat() not in cache][:limit]


def _share_series(days: Mapping[str, dict], iso3: str, category: str) -> list[tuple[str, float]]:
    series = []
    for day, data in days.items():
        c = (data.get("countries") or {}).get(iso3)
        if c and c.get("all", 0) >= 5:
            series.append((day, c.get(category, 0) / c["all"]))
    return series


def zscores(days: Mapping[str, dict], today: date) -> dict[str, dict[str, float | None]]:
    """Per country and category: last 7 days' mean share vs the baseline before it."""
    window_start = (today - timedelta(days=WINDOW_DAYS)).isoformat()
    result: dict[str, dict[str, float | None]] = {}
    codes = {c for data in days.values() for c in (data.get("countries") or {})}
    for iso3 in codes & universe_codes():
        entry: dict[str, float | None] = {}
        for category in CATEGORIES[1:]:
            series = _share_series(days, iso3, category)
            recent = [v for d, v in series if d >= window_start]
            base = [v for d, v in series if d < window_start]
            if len(recent) < 3 or len(base) < MIN_BASELINE:
                entry[category] = None
                continue
            mean = sum(base) / len(base)
            sd = math.sqrt(sum((v - mean) ** 2 for v in base) / (len(base) - 1))
            floor = max(sd, 0.2 * mean, 0.005)
            entry[category] = round((sum(recent) / len(recent) - mean) / floor, 2)
        result[iso3] = entry
    return result


def dyad_trend(days: Mapping[str, dict], pairs: Iterable[tuple[str, str]], today: date) -> dict:
    """Hostile events between watched pairs: last 30 days vs the 30-day average before."""
    recent_from = (today - timedelta(days=30)).isoformat()
    result = {}
    for a, b in pairs:
        key, back = f"{a}>{b}", f"{b}>{a}"
        recent = base = 0
        base_days = 0
        for day, data in days.items():
            n = (data.get("dyads") or {}).get(key, 0) + (data.get("dyads") or {}).get(back, 0)
            if day >= recent_from:
                recent += n
            else:
                base += n
                base_days += 1
        if base_days >= MIN_BASELINE:
            expected = base / base_days * 30
            result[f"{a}-{b}"] = {
                "recent": recent,
                "expected": round(expected, 1),
                "ratio": round((recent + 1) / (expected + 1), 2),
            }
    return result
