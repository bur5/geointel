"""US Department of State travel advisories (levels 1–4, public Consular Affairs API)."""

import html
import re
from collections.abc import Iterable, Mapping

from geointel.risk.countries import resolve_country_name

SOURCE = "U.S. Department of State travel advisories"
URL = "https://cadataapi.state.gov/api/TravelAdvisories"
_LEVEL = re.compile(r"Level\s*([1-4])", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")


def _plain(text: str, limit: int = 700) -> str:
    text = html.unescape(_TAGS.sub(" ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def parse(items: Iterable[Mapping]) -> tuple[dict[str, dict], int]:
    """Return advisories keyed by ISO3 and the number of unresolved entries."""
    result: dict[str, dict] = {}
    unresolved = 0
    for item in items:
        row = {str(k).lower(): v for k, v in item.items()}
        title = str(row.get("title") or "")
        match = _LEVEL.search(title)
        if not match:
            continue
        name = title.split(" - Level")[0].split(" – Level")[0].strip()
        code = resolve_country_name(name)
        if not code:
            unresolved += 1
            continue
        level = int(match.group(1))
        previous = result.get(code)
        if previous and previous["level"] >= level:
            continue
        result[code] = {
            "level": level,
            "title": title,
            "url": row.get("link"),
            "updated": row.get("updated") or row.get("published"),
            "summary": _plain(str(row.get("summary") or "")),
        }
    return result, unresolved
