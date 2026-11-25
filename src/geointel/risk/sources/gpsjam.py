"""GPS/GNSS interference from aircraft navigation-accuracy reports (GPSJam.org daily files).

Each daily file lists H3 hexagons with the number of aircraft reporting good and bad navigation
accuracy (ADS-B). We locate hexagons in countries and track the share of affected aircraft.
"""

import csv
import io
from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import date, timedelta

SOURCE = "GPSJam.org (ADS-B navigation accuracy)"
URLS = (
    "https://gpsjam.org/data/{day}-h3_4.csv",
    "https://gpsjam.org/data/{day}-h3_3.csv",
)
BASELINE_DAYS = 90


def _column(header: list[str], *needles: str) -> int | None:
    for i, name in enumerate(header):
        lowered = name.lower()
        if all(n in lowered for n in needles):
            return i
    return None


def parse_day(
    text: str, locate: Callable[[float, float], str | None], to_latlng: Callable[[str], tuple]
) -> dict[str, dict]:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    header = rows[0]
    hex_i = _column(header, "hex") if _column(header, "hex") is not None else 0
    good_i, bad_i = _column(header, "good"), _column(header, "bad")
    if good_i is None or bad_i is None:
        return {}
    result: dict[str, dict] = defaultdict(lambda: {"good": 0, "bad": 0, "red_hexes": 0})
    for row in rows[1:]:
        try:
            good, bad = int(float(row[good_i])), int(float(row[bad_i]))
            lat, lon = to_latlng(row[hex_i])
        except (IndexError, ValueError, TypeError):
            continue
        code = locate(lat, lon)
        if not code:
            continue
        entry = result[code]
        entry["good"] += good
        entry["bad"] += bad
        if good + bad >= 3 and (bad - 1) / (good + bad) > 0.1:
            entry["red_hexes"] += 1
    return dict(result)


def merge_days(cache: Mapping[str, dict], new: Mapping[str, dict], today: date) -> dict:
    keep_from = (today - timedelta(days=BASELINE_DAYS + 10)).isoformat()
    return dict(sorted((d, v) for d, v in {**cache, **new}.items() if d >= keep_from))


def summary(days: Mapping[str, dict], today: date) -> dict[str, dict]:
    """Share of affected aircraft over the last 7 days and its ratio to the baseline."""
    recent_from = (today - timedelta(days=7)).isoformat()
    recent: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    base: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for day, countries in days.items():
        target = recent if day >= recent_from else base
        for code, v in countries.items():
            t = target[code]
            t[0] += v.get("good", 0)
            t[1] += v.get("bad", 0)
            t[2] += 1
    result = {}
    for code in set(recent) | set(base):
        good, bad, _ = recent.get(code, [0, 0, 0])
        bgood, bbad, bdays = base.get(code, [0, 0, 0])
        share = bad / (good + bad) if good + bad >= 20 else None
        base_share = bbad / (bgood + bbad) if bgood + bbad >= 100 and bdays >= 14 else None
        ratio = None
        if share is not None and base_share is not None:
            ratio = round((share + 0.005) / (base_share + 0.005), 2)
        result[code] = {
            "share": round(share, 4) if share is not None else None,
            "baseline": round(base_share, 4) if base_share is not None else None,
            "ratio": ratio,
        }
    return result
