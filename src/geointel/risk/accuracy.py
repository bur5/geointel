"""Track record of GeoIntel's own scenario forecasts, built from the daily history files.

Every day the pipeline stores ``history/<day>-scenarios.json``. A one-month forecast made on day
``d`` is scored once day ``d + 30`` has passed: the outcome is 1 if the scenario's event happened
in that window according to :data:`RESOLUTIONS`, otherwise 0. Events are entered by hand with a
public source, because no free feed resolves these definitions automatically; the list is checked
when the weekly journal update runs. Until 30 days of history exist the record says so instead of
showing a score.
"""

import json
from datetime import date, timedelta
from pathlib import Path

SCHEMA = "geointel-accuracy-v1"
WINDOW_DAYS = 30

# scenario key -> list of (date the event happened, public source URL)
RESOLUTIONS: dict[str, list[tuple[str, str]]] = {}
RESOLUTIONS_CHECKED = "2026-11-25"


def _happened(key: str, start: date, end: date) -> int:
    for day, _url in RESOLUTIONS.get(key, []):
        if start < date.fromisoformat(day) <= end:
            return 1
    return 0


def load_history(directory: Path) -> dict[str, dict]:
    """Scenario files by day, read from ``<day>-scenarios.json`` names."""
    found: dict[str, dict] = {}
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*-scenarios.json")):
        day = path.name[: -len("-scenarios.json")]
        try:
            date.fromisoformat(day)
            found[day] = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError):
            continue
    return found


def build(history: dict[str, dict], today: date) -> dict:
    series: dict[str, list[dict]] = {}
    titles: dict[str, dict] = {}
    scored: list[dict] = []
    for day in sorted(history):
        made = date.fromisoformat(day)
        for item in history[day].get("scenarios", []):
            key = item.get("key")
            horizons = item.get("horizons") or {}
            if not key or "1m" not in horizons or "1y" not in horizons:
                continue
            titles[key] = {"title_ru": item.get("title_ru"), "title_en": item.get("title_en")}
            series.setdefault(key, []).append(
                {"date": day, "p1m": horizons["1m"]["p"], "p1y": horizons["1y"]["p"]}
            )
            end = made + timedelta(days=WINDOW_DAYS)
            if end <= today:
                p = horizons["1m"]["p"]
                outcome = _happened(key, made, end)
                scored.append(
                    {
                        "key": key,
                        "date": day,
                        "p": p,
                        "outcome": outcome,
                        "brier": round((p - outcome) ** 2, 6),
                    }
                )
    by_key: dict[str, dict] = {}
    for row in scored:
        agg = by_key.setdefault(row["key"], {"n": 0, "events": 0, "brier_sum": 0.0, "p_sum": 0.0})
        agg["n"] += 1
        agg["events"] += row["outcome"]
        agg["brier_sum"] += row["brier"]
        agg["p_sum"] += row["p"]
    summary = {
        key: {
            "n": a["n"],
            "events": a["events"],
            "brier": round(a["brier_sum"] / a["n"], 6),
            "mean_p": round(a["p_sum"] / a["n"], 6),
        }
        for key, a in by_key.items()
    }
    first = min(history) if history else None
    days = (today - date.fromisoformat(first)).days if first else 0
    return {
        "schema": SCHEMA,
        "generated_at": today.isoformat(),
        "first_day": first,
        "history_days": len(history),
        "window_days": WINDOW_DAYS,
        "status": "scoring" if scored else "collecting",
        "first_score_on": (
            (date.fromisoformat(first) + timedelta(days=WINDOW_DAYS)).isoformat() if first else None
        ),
        "days_collected": days,
        "resolutions_checked": RESOLUTIONS_CHECKED,
        "resolutions": {k: [{"date": d, "url": u} for d, u in v] for k, v in RESOLUTIONS.items()},
        "titles": titles,
        "series": series,
        "summary": summary,
        "overall": (
            {
                "n": len(scored),
                "events": sum(r["outcome"] for r in scored),
                "brier": round(sum(r["brier"] for r in scored) / len(scored), 6),
            }
            if scored
            else None
        ),
    }
