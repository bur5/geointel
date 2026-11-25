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


def _value(entry: Mapping | None) -> float | None:
    if not isinstance(entry, Mapping):
        return None
    for key in ("centers", "means", "forecast_values"):
        values = entry.get(key)
        if isinstance(values, int | float):
            values = [values]
        if isinstance(values, list) and values:
            value = values[-1] if key == "forecast_values" else values[0]
            if isinstance(value, int | float) and 0 <= value <= 1:
                return float(value)
    return None


def _probability(question: Mapping) -> float | None:
    """Community probability: the latest aggregate, else the last point of its history."""
    aggregations = question.get("aggregations") or {}
    for method in ("recency_weighted", "unweighted", "metaculus_prediction"):
        agg = aggregations.get(method) or {}
        if not isinstance(agg, Mapping):
            continue
        value = _value(agg.get("latest"))
        if value is None:
            history = agg.get("history") or []
            if isinstance(history, list) and history:
                value = _value(history[-1])
        if value is not None:
            return value
    return None


def _end(post: Mapping, question: Mapping) -> str:
    for source in (question, post):
        for key in ("scheduled_resolve_time", "scheduled_close_time", "actual_close_time"):
            value = source.get(key)
            if isinstance(value, str) and len(value) >= 10:
                return value
    return ""


def has_probability(post: Mapping) -> bool:
    return _probability(post.get("question") or {}) is not None


def diagnose(payload: Mapping) -> str:
    """One line describing why posts in a response were or were not used."""
    reasons = {"ok": 0, "type": 0, "no_p": 0, "no_end": 0}
    sample = ""
    for post in payload.get("results") or []:
        question = post.get("question") or {}
        if question.get("type") not in (None, "binary"):
            reasons["type"] += 1
            continue
        if _probability(question) is None:
            reasons["no_p"] += 1
            if not sample:
                agg = (question.get("aggregations") or {}).get("recency_weighted") or {}
                latest = agg.get("latest") if isinstance(agg, Mapping) else None
                history = agg.get("history") if isinstance(agg, Mapping) else None
                sample = (
                    f" sample: agg_keys={sorted(agg) if isinstance(agg, Mapping) else type(agg)} "
                    f"latest={type(latest).__name__}:"
                    f"{sorted(latest) if isinstance(latest, Mapping) else latest!r:.80} "
                    f"history_len={len(history) if isinstance(history, list) else history!r:.20}"
                )
            continue
        if not _end(post, question):
            reasons["no_end"] += 1
            continue
        reasons["ok"] += 1
    return " ".join(f"{k}={v}" for k, v in reasons.items()) + sample


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
            end = _end(post, question)
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
