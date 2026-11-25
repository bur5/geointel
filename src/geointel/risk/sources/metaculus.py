"""Metaculus community forecasts (API token required; personal use, can be switched off).

Set ``GEOINTEL_DISABLE_METACULUS=1`` to stop using it (licence: personal use only).
"""

from collections.abc import Iterable, Mapping

SOURCE = "Metaculus community prediction"
POSTS_URL = "https://www.metaculus.com/api/posts/"


def search_params(query: str) -> dict[str, str]:
    return {
        "search": query,
        "statuses": "open",
        "forecast_type": "binary",
        "with_cp": "true",
        "limit": "20",
    }


def _probability(question: Mapping) -> float | None:
    aggregations = question.get("aggregations") or {}
    for method in ("recency_weighted", "unweighted", "metaculus_prediction"):
        latest = (aggregations.get(method) or {}).get("latest") or {}
        for key in ("centers", "means", "forecast_values"):
            values = latest.get(key)
            if isinstance(values, list) and values:
                value = values[-1] if key == "forecast_values" else values[0]
                if isinstance(value, int | float) and 0 <= value <= 1:
                    return float(value)
    return None


def questions(payloads: Iterable[Mapping]) -> list[dict]:
    """Open binary questions with a community probability, deduplicated."""
    seen: set = set()
    result: list[dict] = []
    for payload in payloads:
        for post in payload.get("results") or []:
            question = post.get("question") or {}
            if question.get("type") not in (None, "binary"):
                continue
            pid = post.get("id")
            p = _probability(question)
            end = str(
                question.get("scheduled_resolve_time") or post.get("scheduled_resolve_time") or ""
            )
            if pid in seen or p is None or len(end) < 10:
                continue
            seen.add(pid)
            result.append(
                {
                    "question": str(post.get("title") or question.get("title") or "")[:240],
                    "p": round(p, 4),
                    "end": end[:10],
                    "forecasters": int(
                        post.get("nr_forecasters") or question.get("nr_forecasters") or 0
                    ),
                    "url": f"https://www.metaculus.com/questions/{pid}/",
                }
            )
    return result
