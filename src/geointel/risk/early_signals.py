"""Turn the early-warning sources into per-country signs, keeping daily caches between runs."""

import json
from collections.abc import Callable, Mapping
from datetime import date, timedelta
from pathlib import Path

from geointel.risk.sources import early, telegram
from geointel.risk.warning_signs import make_sign


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text()) if path.is_file() else {}
    except ValueError:
        return {}


def _save(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def build(
    *,
    raw: Mapping[str, object],
    cache_in: Path,
    cache_out: Path,
    today: date,
    locate: Callable[[float, float], str | None] | None,
    conflict_countries: set[str],
) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Returns signs per country and a short status note per source."""
    signs: dict[str, list[dict]] = {}
    notes: dict[str, str] = {}

    def add(code: str, sign: dict) -> None:
        signs.setdefault(code, []).append(sign)

    # Internet outages (IODA): today's 7-day summary vs the country's own past summaries.
    ioda_days = _load(cache_in / "ioda.json").get("days", {})
    if raw.get("ioda"):
        ioda_days[today.isoformat()] = raw["ioda"]
    ioda_days = early.merge_series(ioda_days, {}, 90, today)
    _save(cache_out / "ioda.json", {"days": ioda_days})
    latest = ioda_days.get(today.isoformat(), {})
    for code, value in latest.items():
        past = [
            d[code]["score"]
            for day, d in ioda_days.items()
            if day < today.isoformat() and code in d
        ]
        base = sum(past) / len(past) if past else None
        strong = value["score"] > 0 and (
            base is None
            and value["events"] >= 3
            or base is not None
            and value["score"] >= 3 * max(base, 1)
        )
        add(
            code,
            make_sign(
                "internet_outage",
                "active" if strong else "normal",
                f"оценка {value['score']:.0f}, событий {value['events']} за 7 дней",
                f"score {value['score']:.0f}, {value['events']} events in 7 days",
                source="IODA (Georgia Tech)",
            ),
        )
    notes["ioda"] = f"{len(latest)} countries" if latest else "no data today"

    # Fires (NASA FIRMS): daily counts per country, signal only where a conflict is under way.
    firms_days = _load(cache_in / "firms.json").get("days", {})
    new_cells = raw.get("firms") or {}
    if locate is not None:
        cell_country: dict[str, str | None] = {}
        for day, cells in new_cells.items():
            counts: dict[str, int] = {}
            for cell, n in cells.items():
                if cell not in cell_country:
                    lat, lon = map(float, cell.split(","))
                    cell_country[cell] = locate(lat, lon)
                code = cell_country[cell]
                if code:
                    counts[code] = counts.get(code, 0) + n
            firms_days[day] = counts
    firms_days = early.merge_series(firms_days, {}, 60, today)
    _save(cache_out / "firms.json", {"days": firms_days})
    for code in conflict_countries:
        series = {d: float(v.get(code, 0)) for d, v in firms_days.items()}
        stats = early.ratio_to_baseline(series, today, recent_days=7, min_base=14)
        if stats:
            active = stats["ratio"] >= 1.8 and stats["recent"] >= 20
            add(
                code,
                make_sign(
                    "fires_anomaly",
                    "active" if active else "normal",
                    f"{stats['recent']:.0f} в день (норма {stats['baseline']:.0f})",
                    f"{stats['recent']:.0f} a day (normal {stats['baseline']:.0f})",
                    source="NASA FIRMS (VIIRS)",
                ),
            )
    notes["firms"] = f"{len(firms_days)} days"

    # Military aircraft per watched region.
    mil_days = _load(cache_in / "military.json").get("days", {})
    if raw.get("military"):
        mil_days[today.isoformat()] = raw["military"]
    mil_days = early.merge_series(mil_days, {}, 60, today)
    _save(cache_out / "military.json", {"days": mil_days})
    for box, (ru, en, _bbox) in early.WATCH_BOXES.items():
        series = {d: float(v.get(box, 0)) for d, v in mil_days.items()}
        stats = early.ratio_to_baseline(series, today, recent_days=3, min_base=10)
        if not stats:
            continue
        active = stats["ratio"] >= 1.6 and stats["recent"] >= 5
        for code in early.BOX_COUNTRIES[box]:
            add(
                code,
                make_sign(
                    "military_air",
                    "active" if active else "normal",
                    f"{ru}: {stats['recent']:.0f} военных бортов (норма {stats['baseline']:.0f})",
                    f"{en}: {stats['recent']:.0f} military aircraft "
                    f"(normal {stats['baseline']:.0f})",
                    source="airplanes.live (ADS-B)",
                ),
            )
    notes["military"] = f"{len(mil_days)} days"

    # Russian procurement (weekly).
    weeks = {**_load(cache_in / "zakupki.json").get("weeks", {}), **(raw.get("zakupki") or {})}
    weeks = dict(sorted(weeks.items())[-40:])
    _save(cache_out / "zakupki.json", {"weeks": weeks})
    if len(weeks) >= 12:
        ordered = sorted(weeks.items())
        rising = []
        for term in early.ZAKUPKI_TERMS:
            values = [w.get(term, 0) for _, w in ordered]
            recent, base = values[-4:], values[:-4]
            r = (sum(recent) / 4 + 1) / (sum(base) / len(base) + 1)
            if r >= 1.5:
                rising.append(f"{term} ×{r:.1f}")
        add(
            "RUS",
            make_sign(
                "procurement_medical",
                "active" if len(rising) >= 2 else "normal",
                ", ".join(rising) or "без резкого роста",
                ", ".join(rising) or "no sharp rise",
                source="zakupki.gov.ru",
            ),
        )
    notes["zakupki"] = f"{len(weeks)} weeks"

    # Russian-language media on mobilisation and martial law (GDELT DOC, 90-day series).
    for key, sign in (("mobilization", "media_mobilization"), ("martial_law", "media_martial_law")):
        series = (raw.get("media") or {}).get(key) or {}
        stats = early.ratio_to_baseline(series, today, recent_days=7, min_base=30)
        if stats:
            add(
                "RUS",
                make_sign(
                    sign,
                    "active" if stats["z"] >= 2.5 else "normal",
                    f"{stats['recent']:.0f} статей в день (норма {stats['baseline']:.0f}), "
                    f"z = {stats['z']:+.1f}",
                    f"{stats['recent']:.0f} articles a day (normal {stats['baseline']:.0f}), "
                    f"z = {stats['z']:+.1f}",
                    source="GDELT DOC",
                ),
            )

    # Exchange rates (daily snapshots).
    fx_days = {**_load(cache_in / "fx.json").get("days", {}), **(raw.get("fx") or {})}
    fx_days = early.merge_series(fx_days, {}, 120, today)
    _save(cache_out / "fx.json", {"days": fx_days})
    for code, currency in early._CURRENCIES.items():  # noqa: SLF001 - module table
        change = early.fx_change(fx_days, currency, today)
        if change is None:
            continue
        add(
            code,
            make_sign(
                "currency_crash",
                "active" if change["change30"] >= 0.15 else "normal",
                f"{currency}: {change['change30'] * 100:+.1f}% к доллару за 30 дней "
                "(рост = обесценивание)",
                f"{currency}: {change['change30'] * 100:+.1f}% per dollar in 30 days (up = weaker)",
                source="ExchangeRate-API",
            ),
        )
    notes["fx"] = f"{len(fx_days)} days"

    # Food prices (WFP Global Market Monitor).
    for code, item in (raw.get("food") or {}).items():
        if (today - date.fromisoformat(item["date"][:10])).days > 120:
            continue
        change, alert = item.get("change_1m"), str(item.get("alert") or "").lower()
        active = (change is not None and change >= 10) or alert in ("high", "severe", "alert")
        add(
            code,
            make_sign(
                "food_price_spike",
                "active" if active else "normal",
                f"{item['date']}: изменение за месяц {change:+.1f}%"
                if change is not None
                else f"{item['date']}: {alert}",
                f"{item['date']}: 1-month change {change:+.1f}%"
                if change is not None
                else f"{item['date']}: {alert}",
                source="WFP Global Market Monitor",
            ),
        )

    # Telegram keyword share per country.
    tg = telegram.merge(
        _load(cache_in / "telegram.json").get("channels", {}),
        raw.get("telegram") or {},
        today - timedelta(days=90),
    )
    _save(cache_out / "telegram.json", {"channels": tg})
    for code, series in telegram.country_series(tg).items():
        stats = early.ratio_to_baseline(series, today, recent_days=3, min_base=14)
        if stats:
            add(
                code,
                make_sign(
                    "telegram_keywords",
                    "active" if stats["z"] >= 2.5 and stats["ratio"] >= 1.3 else "normal",
                    f"доля постов с ключевыми словами {stats['recent'] * 100:.0f}% "
                    f"(норма {stats['baseline'] * 100:.0f}%)",
                    f"share of keyword posts {stats['recent'] * 100:.0f}% "
                    f"(normal {stats['baseline'] * 100:.0f}%)",
                    source="Telegram (public channels)",
                ),
            )
    notes["telegram"] = f"{len(tg)} channels"
    return signs, notes


def persistence(
    history_path_in: Path, history_path_out: Path, countries: Mapping[str, dict], today: date
) -> dict[str, dict]:
    """Daily record of each country's factor and active signs; returns trends.

    A sign active on most of the last two weeks is a stronger signal than a one-day spike, so
    persistent automated signs get strength × 1.25 (applied by the caller).
    """
    history = _load(history_path_in).get("countries", {})
    stamp = today.isoformat()
    for code, item in countries.items():
        rows = [r for r in history.get(code, []) if r[0] != stamp]
        active = sorted(s["key"] for s in item["signs"] if s["status"] == "active")
        rows.append([stamp, item["max_factor"], active])
        history[code] = [r for r in rows if (today - date.fromisoformat(r[0])).days <= 180]
    _save(history_path_out, {"countries": history})
    trends: dict[str, dict] = {}
    for code, rows in history.items():
        by_day = {r[0]: r for r in rows}

        def factor_at(days: int, by_day=by_day) -> float | None:
            row = by_day.get((today - timedelta(days=days)).isoformat())
            return row[1] if row else None

        last14 = [r for r in rows if 0 < (today - date.fromisoformat(r[0])).days <= 14]
        counts: dict[str, int] = {}
        for r in last14:
            for key in r[2]:
                counts[key] = counts.get(key, 0) + 1
        recent5: dict[str, int] = {}
        for r in rows:
            if 0 <= (today - date.fromisoformat(r[0])).days <= 4:
                for key in r[2]:
                    recent5[key] = recent5.get(key, 0) + 1
        trends[code] = {
            "recent5": recent5,
            "factor_7d": factor_at(7),
            "factor_30d": factor_at(30),
            "persistent": sorted(k for k, n in counts.items() if n >= 10),
            "series": [[r[0], r[1]] for r in rows[-90:]],
        }
    return trends
