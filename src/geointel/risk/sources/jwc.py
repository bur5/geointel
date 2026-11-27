"""Joint War Committee (Lloyd's Market Association / IUA) Listed Areas.

Areas where marine insurers see enhanced war, piracy and terrorism risk. The list is read
from the TT Club page that reproduces the current JWC circular as text (the JWC itself
publishes PDF/Word circulars). Being listed is shown as an observation; a newly listed
country (first seen in the last 60 days of our own archive) lights the sign.
"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping
from datetime import date

from geointel.risk.countries import resolve_country_name

SOURCE = "Joint War Committee Listed Areas (via TT Club)"
URL = "https://www.ttclub.com/listed-area/"
HEADINGS = {"africa", "europe", "middle east", "south america", "asia", "americas", "oceania"}
WATERS = {
    "sea of azov": ["RUS", "UKR"],
    "cabo delgado": ["MOZ"],
}
_NAMES = {"russia": "RUS", "iran": "IRN", "syria": "SYR"}


def _lines(page: str) -> list[str]:
    start = page.find("Last amended")
    end = page.find("Defined Waters", start)
    if start < 0:
        return []
    segment = page[start : end if end > 0 else start + 20000]
    text = html.unescape(re.sub(r"<[^>]+>", "\n", segment)).replace("\xa0", " ")
    return [re.sub(r"\s+", " ", line).strip() for line in text.split("\n") if line.strip()]


def parse(page: str) -> dict:
    lines = _lines(page)
    header = " ".join(lines[:3])
    circular = re.search(r"JWLA-?\s?(\d{3})", header)
    when = re.search(r"on (\d{1,2})(?:st|nd|rd|th)? (\w+) (\d{4})", header)
    issued = None
    if when:
        try:
            from datetime import datetime

            issued = datetime.strptime(" ".join(when.groups()), "%d %B %Y").date().isoformat()
        except ValueError:
            issued = None
    areas: dict[str, dict] = {}
    for line in lines[1:]:
        low = line.lower()
        if low in HEADINGS or low.startswith(
            ("waters as defined", "as per", "30 ", "last amended")
        ):
            continue
        for key, codes in WATERS.items():
            if low.startswith(key):
                for code in codes:
                    areas.setdefault(code, {"entry": line, "partial": True})
                break
        else:
            name = re.split(r",| but | including ", line, maxsplit=1)[0].strip()
            code = _NAMES.get(name.lower()) or resolve_country_name(name)
            if code:
                partial = name != line and ("only" in low or "waters" in low)
                if code not in areas or areas[code]["partial"]:
                    areas[code] = {"entry": line, "partial": partial}
    return {
        "circular": f"JWLA-{circular.group(1)}" if circular else None,
        "issued": issued,
        "areas": areas,
    }


def with_first_seen(current: Mapping, previous: Mapping | None, today: date) -> dict:
    """Carry each country's first-seen date across days; unknown on the first run."""
    seen = dict((previous or {}).get("first_seen") or {})
    first_run = previous is None or not seen
    for code in current.get("areas", {}):
        if code not in seen:
            seen[code] = None if first_run else today.isoformat()
    seen = {k: v for k, v in seen.items() if k in current.get("areas", {})}
    return {**current, "first_seen": seen}
