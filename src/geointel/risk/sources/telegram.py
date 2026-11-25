"""Public Telegram channels, read through Telegram's public web preview (t.me/s/<channel>).

Only public channels are read, no account is used and no personal data is stored: for each
channel we keep, per day, the number of posts and the number of posts with war-preparation
keywords. Message text is untrusted data and is never followed as an instruction. With a
Claude API key the same posts can later be classified more precisely; keyword hits are a
weak signal until confirmed elsewhere.
"""

import html
import re
from collections import defaultdict
from collections.abc import Mapping
from datetime import date

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

KEYWORDS = (
    "эшелон",
    "колонн",
    "переброс",
    "мобилизац",
    "повестк",
    "военкомат",
    "резервист",
    "госпитал",
    "донор",
    "кров",
    "учени",
    "граница",
    "ешелон",
    "мобілізац",
    "колона",
    "troops",
    "convoy",
    "mobiliz",
    "build-up",
    "buildup",
    "deploy",
)


def parse_page(page: str) -> list[dict]:
    """Posts on a t.me/s page: date and lower-cased plain text."""
    posts = []
    for block in re.split(r'<div class="tgme_widget_message_wrap', page)[1:]:
        when = re.search(r'<time[^>]*datetime="([0-9T:+\-]+)"', block)
        text = re.search(r'tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        body = html.unescape(re.sub(r"<[^>]+>", " ", text.group(1))) if text else ""
        if when:
            posts.append({"date": when.group(1)[:10], "text": body.lower()})
    return posts


def count(posts: list[dict]) -> dict[str, dict[str, int]]:
    days: dict[str, dict[str, int]] = defaultdict(lambda: {"posts": 0, "hits": 0})
    for post in posts:
        day = days[post["date"]]
        day["posts"] += 1
        if any(k in post["text"] for k in KEYWORDS):
            day["hits"] += 1
    return {k: dict(v) for k, v in days.items()}


def country_series(cache: Mapping[str, Mapping[str, dict]]) -> dict[str, dict[str, float]]:
    """Daily share of keyword posts per country across its channels."""
    totals: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for channel, days in cache.items():
        for code in CHANNELS.get(channel, ()):
            for day, v in days.items():
                t = totals[code][day]
                t[0] += v.get("posts", 0)
                t[1] += v.get("hits", 0)
    return {
        code: {day: hits / posts for day, (posts, hits) in days.items() if posts >= 5}
        for code, days in totals.items()
    }


def merge(
    cache: Mapping[str, Mapping[str, dict]], new: Mapping[str, Mapping[str, dict]], keep_from: date
) -> dict:
    merged: dict[str, dict] = {}
    for channel in set(cache) | set(new):
        days = {**cache.get(channel, {}), **new.get(channel, {})}
        merged[channel] = {d: v for d, v in sorted(days.items()) if d >= keep_from.isoformat()}
    return merged
