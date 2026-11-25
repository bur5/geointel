"""Daily Telegram digest for the Owner: what changed since the previous run.

Sent only when the repository secrets ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` exist and
something material changed (or on Mondays, as a weekly summary). The token is read from the
environment and never printed or stored. Message text is built only from GeoIntel's own files.
"""

import json
import os
from collections.abc import Mapping
from datetime import date

SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
SITE_URL = "https://bur5.github.io/geointel/"
PRIORITY = ("EST", "LVA", "LTU", "POL", "FIN", "BLR", "UKR", "RUS", "MDA", "GEO", "IRN", "IRQ")
NAMES_RU = {
    "EST": "Эстония",
    "LVA": "Латвия",
    "LTU": "Литва",
    "POL": "Польша",
    "FIN": "Финляндия",
    "BLR": "Беларусь",
    "UKR": "Украина",
    "RUS": "Россия",
    "MDA": "Молдова",
    "GEO": "Грузия",
    "IRN": "Иран",
    "IRQ": "Ирак",
}
# a change of the yearly probability counts when it is at least 1 percentage point and 15%
ABS_CHANGE, REL_CHANGE = 0.01, 0.15


def _pct(p: float) -> str:
    return f"{p * 100:.1f}%".replace(".", ",")


def scenario_changes(today: Mapping, previous: Mapping | None) -> list[str]:
    before = {s["key"]: s for s in (previous or {}).get("scenarios", [])}
    lines = []
    for s in today.get("scenarios", []):
        old = before.get(s["key"])
        now = s["horizons"]["1y"]["p"]
        if old is None:
            continue
        was = old["horizons"]["1y"]["p"]
        if abs(now - was) >= ABS_CHANGE and abs(now - was) >= REL_CHANGE * max(was, 1e-6):
            arrow = "▲" if now > was else "▼"
            lines.append(f"{arrow} {s['title_ru']}: {_pct(was)} → {_pct(now)} за год")
    return lines


LEVEL_RU = {"green": "фон", "yellow": "повышенный", "orange": "высокий", "red": "ТРЕВОГА"}
ORDER = ("green", "yellow", "orange", "red")


def alert_changes(today: Mapping, previous: Mapping | None) -> list[str]:
    before = {s["key"]: s.get("alert") for s in (previous or {}).get("scenarios", [])}
    lines = []
    for s in today.get("scenarios", []):
        now, was = s.get("alert"), before.get(s["key"])
        if not now or not was or now["level"] == was["level"]:
            continue
        arrow = "▲" if ORDER.index(now["level"]) > ORDER.index(was["level"]) else "▼"
        lines.append(
            f"{arrow} {s['title_ru']}: {LEVEL_RU[was['level']]} → {LEVEL_RU[now['level']]}"
        )
    return lines


def new_signs(
    signals: Mapping, history: Mapping[str, list], catalogue: Mapping[str, Mapping]
) -> list[str]:
    """Signs active today in priority countries that were not active in the previous record."""
    lines = []
    for code in PRIORITY:
        entry = signals.get("countries", {}).get(code)
        if not entry:
            continue
        rows = sorted(history.get(code, []), key=lambda r: r[0])
        today_rows = [r for r in rows if r[0] == signals.get("generated_at", "")[:10]]
        earlier = [r for r in rows if r not in today_rows]
        before = set(earlier[-1][2]) if earlier else None
        if before is None:
            continue
        for sign in entry.get("signs", []):
            if sign.get("status") != "active" or sign["key"] in before:
                continue
            label = (catalogue.get(sign["key"]) or {}).get("label_ru", sign["key"])
            value = sign.get("value_ru") or sign.get("summary_ru") or ""
            lines.append(
                f"• {NAMES_RU.get(code, code)}: {label}" + (f" — {value}" if value else "")
            )
    return lines


def digest(
    scenarios: Mapping,
    previous: Mapping | None,
    signals: Mapping,
    history: Mapping[str, list],
    today: date,
    force: bool = False,
) -> str | None:
    """``force`` builds the weekly-style message even when nothing changed (test runs)."""
    catalogue = {c["key"]: c for c in signals.get("catalogue", [])}
    changes = alert_changes(scenarios, previous) + scenario_changes(scenarios, previous)
    signs = new_signs(signals, history, catalogue)
    weekly = today.weekday() == 0 or force
    if not changes and not signs and not weekly:
        return None
    parts = [f"GeoIntel, {today.strftime('%d.%m.%Y')}" + (" — пробная отправка" if force else "")]
    if changes:
        parts.append("Изменились уровни тревоги и вероятности:\n" + "\n".join(changes))
    if signs:
        parts.append("Новые признаки:\n" + "\n".join(signs[:15]))
    if weekly:
        key = {s["key"]: s for s in scenarios.get("scenarios", [])}
        top = [
            f"{key[k]['title_ru']}: {_pct(key[k]['horizons']['1y']['p'])} за год"
            for k in ("russia_nato", "russia_nato_war", "belarus_front", "ukraine_ceasefire")
            if k in key
        ]
        if top:
            parts.append("Неделя — главное:\n" + "\n".join(top))
    if len(parts) == 1:
        parts.append("Существенных изменений нет.")
    parts.append(SITE_URL)
    return "\n\n".join(parts)[:4000]


def send(text: str, client=None) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[notify] not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing)")
        return False
    import httpx

    http = client or httpx.Client(timeout=30)
    response = http.post(
        SEND_URL.format(token=token),
        json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
    )
    if response.status_code != 200:
        print(f"[notify] Telegram answered {response.status_code}")
        return False
    print("[notify] sent")
    return True


def load(path) -> dict | None:
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except (OSError, ValueError):
        return None
