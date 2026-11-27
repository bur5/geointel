"""EASA Conflict Zone Information Bulletins (CZIBs).

A CZIB is issued for airspace that the EU aviation security risk group judges high risk.
New or revised bulletins preceded some escalations (for example February 2022), but their
predictive value is not yet tested, so GeoIntel shows them as an observation (multiplier 1).
"""

from __future__ import annotations

import html
import re
from datetime import date

from geointel.risk.countries import resolve_country_name

SOURCE = "EASA Conflict Zone Information Bulletins"
URL = "https://www.easa.europa.eu/en/domains/air-operations/czibs"
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TAG = re.compile(r"<[^>]+>")
_NAMES = {
    "the russian federation": "RUS",
    "jordan": "JOR",
    "iran": "IRN",
    "syria": "SYR",
    "north korea": "PRK",
    "south sudan": "SSD",
}


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", fragment))).strip()


def _date(text: str) -> str | None:
    match = re.match(r"(\d{2})/(\d{2})/(\d{4})", text.strip())
    if not match:
        return None
    day, month, year = (int(x) for x in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def country_of(title: str) -> tuple[str | None, bool]:
    """(ISO3, partial) for "Airspace of X[ – part]"; multi-country areas give (None, False)."""
    match = re.match(r"(?:airspace of\s+)(.+)$", title.strip(), re.I)
    if not match:
        return None, False
    pieces = re.split(r"\s+[–-]\s+|,\s+", match.group(1), maxsplit=1)
    name = pieces[0].strip()
    partial = len(pieces) > 1
    key = name.lower()
    code = _NAMES.get(key) or resolve_country_name(re.sub(r"^the\s+", "", name, flags=re.I))
    return code, partial


def parse(page: str) -> list[dict]:
    bulletins = []
    for row in _ROW.findall(page):
        title = re.search(r'class="cz-title">(.*?)</div>', row, re.S)
        if not title:
            continue
        number = re.search(r'class="czib_number">(.*?)</div>', row, re.S)
        status = re.search(r"cz-status-(\w+)", row)
        cells = [_text(c) for c in _TD.findall(row)]
        name = _text(title.group(1))
        iso3, partial = country_of(name)
        bulletins.append(
            {
                "title": name,
                "number": _text(number.group(1)) if number else None,
                "active": bool(status and status.group(1).lower() == "active"),
                "issued": _date(cells[0]) if cells else None,
                "revised": _date(cells[1]) if len(cells) > 1 else None,
                "valid_until": _date(cells[2]) if len(cells) > 2 else None,
                "iso3": iso3,
                "partial": partial,
            }
        )
    return bulletins


def current(bulletins: list[dict], today: date) -> dict[str, dict]:
    """Active bulletins per country, with whether it was issued or revised in 30 days."""
    out: dict[str, dict] = {}
    for item in bulletins:
        code = item.get("iso3")
        until = item.get("valid_until")
        if not code or not item.get("active") or (until and until < today.isoformat()):
            continue
        latest = max(d for d in (item.get("issued"), item.get("revised"), "0000") if d)
        fresh = latest != "0000" and (today - date.fromisoformat(latest)).days <= 30
        prev = out.get(code)
        if prev and prev["latest"] >= latest:
            continue
        out[code] = {**item, "latest": latest, "fresh": fresh}
    return out
