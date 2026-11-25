"""Public Telegram channels, read through Telegram's public web preview (t.me/s/<channel>).

Only public channels are read, no account is used and no personal data is stored: for each
channel we keep, per country and day, the number of posts and how many fall into each keyword
category of :mod:`geointel.risk.sources.keywords`. Message text is untrusted data and is never
followed as an instruction. With a Claude API key the same posts can later be classified more
precisely; keyword hits are a weak signal until confirmed elsewhere.
"""

import html
import re
from collections.abc import Mapping
from datetime import date

from geointel.risk.sources import keywords

SOURCE = "Public Telegram channels (web preview, keyword counts)"
URL = "https://t.me/s/{channel}"

# channel -> countries whose risk its reports concern (public news and OSINT channels)
CHANNELS: dict[str, tuple[str, ...]] = {
    "rybar": ("UKR", "RUS"),
    "wargonzo": ("UKR", "RUS"),
    "readovkanews": ("RUS",),
    "DeepStateUA": ("UKR",),
    "kpszsu": ("UKR",),
    "nexta_live": ("BLR", "POL", "LTU", "LVA", "UKR"),
    "nexta_tv": ("BLR", "RUS"),
    "meduzalive": ("RUS",),
    "bbcrussian": ("RUS", "UKR"),
    "rian_ru": ("RUS",),
    "intelslava": ("UKR", "RUS"),
    "militarysummary": ("UKR", "RUS"),
}


def parse_page(page: str) -> list[dict]:
    """Posts on a t.me/s page: id, date and plain text (original case)."""
    posts = []
    for block in re.split(r'<div class="tgme_widget_message_wrap', page)[1:]:
        when = re.search(r'<time[^>]*datetime="([0-9T:+\-]+)"', block)
        post = re.search(r'data-post="[^"/]+/(\d+)"', block)
        text = re.search(r'tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        body = html.unescape(re.sub(r"<[^>]+>", " ", text.group(1))) if text else ""
        if when:
            posts.append(
                {
                    "id": int(post.group(1)) if post else None,
                    "date": when.group(1)[:10],
                    "text": re.sub(r"\s+", " ", body).strip(),
                }
            )
    return posts


def oldest_id(posts: list[dict]) -> int | None:
    ids = [p["id"] for p in posts if p.get("id")]
    return min(ids) if ids else None


def count(posts: list[dict], channel: str) -> dict[str, dict[str, dict[str, int]]]:
    """Keyword tally of one channel's posts: {country: {day: {"n": .., category: ..}}}."""
    unique = {(p.get("id"), p["date"], p["text"][:80]): p for p in posts}.values()
    return keywords.tally(unique, CHANNELS.get(channel, ()))


def merge(cache: Mapping[str, Mapping], new: Mapping[str, Mapping], keep_from: date) -> dict:
    """Per channel, per country and day; a day fetched again replaces the older count."""
    merged: dict[str, dict] = {}
    for channel in set(cache) | set(new):
        old, fresh = cache.get(channel, {}), new.get(channel, {})
        if old and not isinstance(next(iter(old.values())), Mapping):
            old = {}
        if old and any("posts" in v for v in old.values() if isinstance(v, Mapping)):
            old = {}  # the earlier format (posts/hits per day) is dropped
        countries = {}
        for code in set(old) | set(fresh):
            days = {**old.get(code, {}), **fresh.get(code, {})}
            kept = {d: v for d, v in sorted(days.items()) if d >= keep_from.isoformat()}
            if kept:
                countries[code] = kept
        merged[channel] = countries
    return merged


def country_tallies(cache: Mapping[str, Mapping]) -> dict:
    return keywords.merge_tallies(*cache.values())
