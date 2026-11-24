"""Polymarket prediction-market prices (public Gamma API, no key).

Market text is untrusted data: it is only matched against keyword lists and copied into the
output as a labelled quote, never interpreted as instructions.
"""

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

SOURCE = "Polymarket (Gamma public search)"
SEARCH_URL = "https://gamma-api.polymarket.com/public-search"


def search_params(query: str) -> dict[str, str]:
    return {"q": query, "events_status": "active", "limit_per_type": "25"}


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def markets(payloads: Iterable[Mapping]) -> list[dict]:
    """Flatten search responses into open binary markets with a Yes price."""
    seen: set[str] = set()
    result: list[dict] = []
    for payload in payloads:
        for event in payload.get("events") or []:
            for market in event.get("markets") or []:
                key = str(market.get("id") or market.get("conditionId") or market.get("question"))
                if key in seen or market.get("closed") is True:
                    continue
                outcomes = [str(o).strip().lower() for o in _as_list(market.get("outcomes"))]
                prices = [_float(p) for p in _as_list(market.get("outcomePrices"))]
                if "yes" not in outcomes or len(prices) != len(outcomes):
                    continue
                price = prices[outcomes.index("yes")]
                end = _date(market.get("endDate") or event.get("endDate"))
                if price is None or end is None:
                    continue
                seen.add(key)
                result.append(
                    {
                        "question": str(market.get("question") or event.get("title") or "")[:240],
                        "event": str(event.get("title") or "")[:240],
                        "slug": str(event.get("slug") or ""),
                        "p": round(price, 4),
                        "end": end.date().isoformat(),
                        "volume": _float(market.get("volume") or market.get("volumeNum")) or 0.0,
                        "week_change": _float(market.get("oneWeekPriceChange")),
                        "month_change": _float(market.get("oneMonthPriceChange")),
                    }
                )
    return result


def matches(question: str, groups: Iterable[Iterable[str]], exclude: Iterable[str] = ()) -> bool:
    """Every keyword group must match (any word of a group); no excluded word may appear."""
    text = f" {question.lower()} "
    if any(word in text for word in exclude):
        return False
    return all(any(word in text for word in group) for group in groups)


def url(slug: str) -> str:
    return f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"
