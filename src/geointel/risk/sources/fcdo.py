"""UK Foreign, Commonwealth & Development Office travel advice (GOV.UK Content API)."""

import html
import re
from collections.abc import Mapping

from geointel.risk.countries import resolve_country_name

SOURCE = "UK FCDO foreign travel advice"
INDEX_URL = "https://www.gov.uk/api/content/foreign-travel-advice"
_TAGS = re.compile(r"<[^>]+>")
LEVELS = {
    "avoid_all_travel_to_whole_country": 4,
    "avoid_all_but_essential_travel_to_whole_country": 3,
    "avoid_all_travel_to_parts": 2,
    "avoid_all_but_essential_travel_to_parts": 2,
}
_ALIASES = {"the occupied palestinian territories": "Palestine", "usa": "United States"}


def child_urls(index: Mapping) -> list[str]:
    children = (index.get("links") or {}).get("children") or []
    return [c["api_url"] for c in children if c.get("api_url")]


def _lines(body: str) -> list[str]:
    text = html.unescape(_TAGS.sub("\n", body or ""))
    return [re.sub(r"\s+", " ", line).strip() for line in text.split("\n") if line.strip()]


def parse_country(page: Mapping) -> tuple[str | None, dict | None]:
    title = str(page.get("title") or "").replace(" travel advice", "").strip()
    name = _ALIASES.get(title.lower(), title)
    code = resolve_country_name(name)
    if not code:
        return None, None
    details = page.get("details") or {}
    statuses = [s for s in details.get("alert_status") or [] if s in LEVELS]
    level = max((LEVELS[s] for s in statuses), default=1)
    restricted: list[str] = []
    for part in details.get("parts") or []:
        if "warning" not in str(part.get("slug", "")):
            continue
        capture = False
        for line in _lines(part.get("body", "")):
            if "advises against" in line.lower():
                restricted.append(line)
                capture = True
            elif capture and len(line) < 160 and len(restricted) < 24:
                restricted.append("• " + line)
            else:
                capture = False
    # "Parts" can mean almost the whole country: Ukraine is advised against all travel to
    # "all other regions" except a few in the west. Such wording counts as the whole country.
    text = " ".join(restricted).lower()
    if level == 2 and re.search(r"against all travel to (?:all other|the rest of|the whole)", text):
        level = 4
    elif level == 2 and re.search(
        r"against all but essential travel to (?:all other|the rest of|the whole)", text
    ):
        level = 3
    return code, {
        "level": level,
        "partial": any(s.endswith("_parts") for s in statuses),
        "statuses": statuses,
        "url": page.get("web_url"),
        "updated": page.get("public_updated_at"),
        "restrictions": restricted[:24],
    }
