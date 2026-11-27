"""Travel advice of Canada (Global Affairs) and Germany (Auswärtiges Amt), on a 1–4 scale.

US (State Department) and UK (FCDO) advice are loaded elsewhere; together they feed the
foreign-ministry median in ``danger.py``. Australia's Smartraveller export was unreachable
from GitHub runners in November 2026 and is not used.
"""

from collections.abc import Mapping
from datetime import UTC, datetime

from geointel.risk.countries import universe

CANADA_URL = "https://data.international.gc.ca/travel-voyage/index-alpha-eng.json"
GERMANY_URL = "https://www.auswaertiges-amt.de/opendata/travelwarning"
CANADA_PAGE = "https://travel.gc.ca/destinations/{slug}"
GERMANY_PAGE = "https://www.auswaertiges-amt.de/de/service/laender/{slug}"
SOURCE = "Global Affairs Canada; Auswärtiges Amt (open data)"


def _iso2_map() -> dict[str, str]:
    return {c.iso2: c.iso3 for c in universe()}


def parse_canada(payload: Mapping) -> dict[str, dict]:
    """advisory-state 0 normal precautions … 3 avoid all travel → 1–4."""
    iso = _iso2_map()
    result = {}
    for code, item in ((payload or {}).get("data") or {}).items():
        iso3 = iso.get(str(item.get("country-iso") or code).upper())
        try:
            state = int(item.get("advisory-state"))
        except (TypeError, ValueError):
            continue
        if not iso3 or not 0 <= state <= 3:
            continue
        eng = item.get("eng") or {}
        result[iso3] = {
            "level": state + 1,
            "partial": bool(item.get("has-regional-advisory")),
            "url": CANADA_PAGE.format(slug=eng.get("url-slug")) if eng.get("url-slug") else None,
            "updated": ((item.get("date-published") or {}).get("date") or None),
            "summary": str(eng.get("advisory-text") or ""),
        }
    return result


def parse_germany(payload: Mapping) -> dict[str, dict]:
    """Travel warning 4 (partial: regional warning → 3 for the country), security-situation
    warning 3 (partial → 2), otherwise 1."""
    codes = {c.iso3 for c in universe()}
    result = {}
    for key, item in ((payload or {}).get("response") or {}).items():
        if not isinstance(item, Mapping):
            continue
        iso3 = str(item.get("iso3CountryCode") or "").upper()
        if iso3 not in codes:
            continue
        if item.get("warning"):
            level, partial = 4, False
        elif item.get("partialWarning"):
            level, partial = 3, True
        elif item.get("situationWarning"):
            level, partial = 3, False
        elif item.get("situationPartWarning"):
            level, partial = 2, True
        else:
            level, partial = 1, False
        stamp = item.get("lastModified")
        updated = datetime.fromtimestamp(int(stamp), UTC).date().isoformat() if stamp else None
        result[iso3] = {
            "level": level,
            "partial": partial,
            "url": f"https://www.auswaertiges-amt.de/de/service/laender/-/{key}",
            "updated": updated,
            "summary": str(item.get("title") or ""),
        }
    return result
