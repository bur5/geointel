"""Command line: ``python -m geointel.risk fetch|build``."""

import argparse
import json
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from geointel.risk.model import TypeHistory
from geointel.risk.taxonomy import EventType


def load_histories(
    raw_dir: Path, reference_year: int, extras: dict | None = None
) -> tuple[dict[EventType, TypeHistory | None], list[dict], list[dict]]:
    """Parse whatever sources were fetched successfully; failures stay unavailable.

    Returns event-type histories, source status records and located hazard events.
    """
    from geointel.risk.sources import (
        advisories,
        coups,
        elections,
        exposure,
        fcdo,
        fts,
        gdacs,
        gdelt,
        metaculus,
        migration,
        ncei_tsunami,
        newswire,
        outlook,
        polymarket,
        sentinel,
        trade,
        ucdp_acd,
        usgs,
        worldbank,
    )

    extras = extras if extras is not None else {}

    manifest_path = raw_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    histories: dict[EventType, TypeHistory | None] = {}
    sources: list[dict] = []
    hazard_events: list[dict] = []

    def ucdp(path: Path) -> None:
        version = manifest["ucdp_acd"].get("version")
        internal, interstate = ucdp_acd.parse(
            ucdp_acd.read_csv_bytes(path.read_bytes()), version=version
        )
        histories[EventType.INTERNAL_ARMED_CONFLICT] = internal
        histories[EventType.INTERSTATE_CONFLICT] = interstate
        text = ucdp_acd.read_csv_bytes(path.read_bytes())
        extras["dyads"] = ucdp_acd.dyad_years(text)
        extras["ucdp_last_year"] = interstate.end_year
        extras["war_intensity"] = ucdp_acd.latest_intensity(text)
        extras["active_interstate"] = {
            code
            for code, years in interstate.years_with_event.items()
            if interstate.end_year in years
        }

    def coup(path: Path) -> None:
        text = path.read_bytes().decode("utf-8", errors="replace")
        histories[EventType.COUP_ATTEMPT] = coups.parse_any(text, reference_year)

    def quakes(path: Path) -> None:
        text = path.read_text()
        histories[EventType.MAJOR_EARTHQUAKE] = usgs.parse(text, reference_year)
        hazard_events.extend(usgs.events(text))

    def gdacs_alerts(path: Path) -> None:
        features = json.loads(path.read_text()).get("features", [])
        extras["hazard_alerts"] = gdacs.current_alerts(features, datetime.now(UTC).date())
        events = gdacs.normalize_all(features)
        histories.update(gdacs.histories(events, reference_year))
        hazard_events.extend(events)

    def tsunamis(path: Path) -> None:
        events = ncei_tsunami.normalize_all(json.loads(path.read_text()))
        histories[EventType.TSUNAMI] = ncei_tsunami.history(events, reference_year)
        hazard_events.extend(events)

    def economy(path: Path) -> None:
        payload = json.loads(path.read_text())
        histories[EventType.ECONOMIC_CRISIS] = worldbank.history(
            payload.get(worldbank.GDP_GROWTH), payload.get(worldbank.INFLATION)
        )

    def humanitarian(path: Path) -> None:
        payload = {int(k): v for k, v in json.loads(path.read_text()).items()}
        histories[EventType.HUMANITARIAN_CRISIS] = fts.history(payload)

    def travel(path: Path) -> None:
        extras["advisories"], _ = advisories.parse(json.loads(path.read_text()))

    def structure(path: Path) -> None:
        extras["profiles"] = exposure.latest(json.loads(path.read_text()))

    def imf(path: Path) -> None:
        extras["outlook"] = outlook.imf_outlook(json.loads(path.read_text()), reference_year)

    def democracy(path: Path) -> None:
        extras["democracy"] = outlook.owid_latest(path.read_text())

    def gpr(path: Path) -> None:
        columns, months = outlook.read_gpr_xls(path.read_bytes())
        extras["gpr"] = outlook.gpr_country_series(columns, months)

    def votes(path: Path) -> None:
        extras["elections"] = elections.parse(json.loads(path.read_text()))

    def uk_travel(path: Path) -> None:
        parsed = {}
        for page in json.loads(path.read_text()):
            code, entry = fcdo.parse_country(page)
            if code and entry:
                parsed[code] = entry
        extras["fcdo"] = parsed

    def defence(path: Path) -> None:
        extras["milex"] = trade.milex_summary(trade.owid_series(path.read_text()))

    def markets(path: Path) -> None:
        extras["markets"] = polymarket.markets(json.loads(path.read_text())["responses"])

    def displaced(path: Path) -> None:
        payload = json.loads(path.read_text())
        extras["displacement"] = migration.displacement(
            migration.merge_pages(payload["pages"]), payload["year"]
        )

    def asylum(path: Path) -> None:
        extras["asylum"] = migration.asylum_trend(
            migration.jsonstat_series(json.loads(path.read_text()))
        )

    def bilateral(path: Path) -> None:
        payload = json.loads(path.read_text())
        codes = {int(k): v for k, v in payload["codes"].items()}
        exports = trade.exports_by_partner(payload["responses"], codes)
        extras["trade"] = trade.trade_links(exports)
        periods = [r.get("period") for r in payload["responses"] if r.get("period")]
        extras["trade_year"] = max(set(periods), key=periods.count) if periods else None

    def events_news(path: Path) -> None:
        extras["gdelt_new"] = json.loads(path.read_text()).get("days", {})

    def gps(path: Path) -> None:
        extras["gps_files"] = json.loads(path.read_text()).get("files", {})

    def community(path: Path) -> None:
        extras["community"] = metaculus.questions(json.loads(path.read_text())["payloads"])

    def radar(path: Path) -> None:
        payload = json.loads(path.read_text())
        extras["radar"] = {
            key: sentinel.series(response) for key, response in payload.get("sites", {}).items()
        }

    def early_raw(key: str, kind: str = "json") -> Callable[[Path], None]:
        def load(path: Path) -> None:
            from geointel.risk.sources import early as early_src

            raw = extras.setdefault("early_raw", {})
            if kind == "food":
                raw[key] = early_src.food_prices(path.read_text(errors="replace"))
                return
            payload = json.loads(path.read_text())
            raw[key] = {
                "ioda": lambda p: p.get("countries", {}),
                "firms": lambda p: p.get("days", {}),
                "military": lambda p: p.get("counts", {}),
                "media": lambda p: p.get("series", {}),
                "fx": lambda p: p.get("days", {}),
                "telegram": lambda p: p.get("channels", {}),
            }[key](payload)

        return load

    def news(path: Path) -> None:
        extras["news_new"] = json.loads(path.read_text()).get("entries", [])

    def admin_regions(path: Path) -> None:
        from geointel.risk.regions import RegionIndex, annotate

        index = RegionIndex.from_bytes(path.read_bytes())
        extras["region_index"] = index
        annotate(hazard_events, index)

    loaders: list[tuple[str, str, Callable[[Path], None]]] = [
        ("ucdp_acd", ucdp_acd.SOURCE, ucdp),
        ("coups", coups.CLINE_SOURCE + " / Powell & Thyne", coup),
        ("usgs", usgs.SOURCE, quakes),
        ("gdacs", gdacs.SOURCE, gdacs_alerts),
        ("tsunami", ncei_tsunami.SOURCE, tsunamis),
        ("worldbank", worldbank.SOURCE, economy),
        ("fts", fts.SOURCE, humanitarian),
        ("advisories", advisories.SOURCE, travel),
        ("exposure", exposure.SOURCE, structure),
        ("imf", outlook.IMF_SOURCE, imf),
        ("vdem", outlook.VDEM_SOURCE, democracy),
        ("gpr", outlook.GPR_SOURCE, gpr),
        ("elections", elections.SOURCE, votes),
        ("fcdo", fcdo.SOURCE, uk_travel),
        ("milex", trade.MILEX_SOURCE, defence),
        ("markets", polymarket.SOURCE, markets),
        ("unhcr", migration.UNHCR_SOURCE, displaced),
        ("eurostat", migration.EUROSTAT_SOURCE, asylum),
        ("trade", trade.TRADE_SOURCE, bilateral),
        ("gdelt", gdelt.SOURCE, events_news),
        ("gpsjam", "GPSJam.org (ADS-B navigation accuracy)", gps),
        ("metaculus", metaculus.SOURCE, community),
        ("sentinel", sentinel.SOURCE, radar),
        ("newswire", newswire.SOURCE, news),
        ("ioda", "IODA internet outages (Georgia Tech)", early_raw("ioda")),
        ("firms", "NASA FIRMS fire detections (VIIRS)", early_raw("firms")),
        ("military", "airplanes.live military aircraft (ADS-B)", early_raw("military")),
        ("media", "GDELT DOC Russian-language media volume", early_raw("media")),
        ("fx", "ExchangeRate-API daily rates", early_raw("fx")),
        ("food", "WFP Global Market Monitor (HDX)", early_raw("food", "food")),
        ("telegram", "Public Telegram channels", early_raw("telegram")),
        ("regions", "Natural Earth admin-1 regions", admin_regions),  # must stay last
    ]
    for key, name, loader in loaders:
        info = manifest.get(key, {})
        path = raw_dir / info.get("file", "")
        error = None
        if info.get("status") == "ok" and path.is_file():
            try:
                loader(path)
            except Exception as exc:  # noqa: BLE001
                error = f"parse error: {type(exc).__name__}: {exc}"
        else:
            error = "; ".join(info.get("errors", [])) or "not fetched"
        sources.append(
            {
                "key": key,
                "name": name,
                "url": info.get("url"),
                "version": info.get("version"),
                "retrieved_at": info.get("retrieved_at"),
                "status": "failed" if error else "ok",
                "error": error,
            }
        )
    return histories, sources, hazard_events


def _cache_dirs() -> tuple[Path, Path]:
    import os

    return (
        Path(os.environ.get("GEOINTEL_CACHE_DIR", "data/cache")),
        Path(os.environ.get("GEOINTEL_CACHE_OUT", "data/cache-out")),
    )


def _load(path: Path) -> dict | list:
    try:
        return json.loads(path.read_text()) if path.is_file() else {}
    except ValueError:
        return {}


def build_signal_layer(snapshot: dict, extras: dict, sources: list[dict], now) -> tuple[dict, dict]:
    """Merge daily caches, compute warning signs per country and inputs for scenarios."""
    from geointel.risk.scenarios import CATALOGUE
    from geointel.risk.sources import gdelt, gpsjam, newswire, sentinel
    from geointel.risk.warning_signs import build_signals

    cache_in, cache_out = _cache_dirs()
    cache_out.mkdir(parents=True, exist_ok=True)
    today = now.date()
    status = {s["key"]: s["status"] for s in sources}

    # GDELT
    days = gdelt.merge_days(
        _load(cache_in / "gdelt.json").get("days", {}), extras.get("gdelt_new", {}), today
    )
    (cache_out / "gdelt.json").write_text(json.dumps({"days": days}, separators=(",", ":")))
    gdelt_z = gdelt.zscores(days, today) if days else None
    pairs = set()
    for scenario in CATALOGUE:
        for a in scenario.side_a:
            for e in scenario.exposures:
                if e.role in ("party", "frontline"):
                    pairs |= {(a, c) for c in e.countries if c != a}
    dyad_trend = gdelt.dyad_trend(days, sorted(pairs), today) if days else {}
    print(f"[signals] gdelt days={len(days)} countries_with_z={len(gdelt_z or {})}")

    # GPS interference
    gps_days = _load(cache_in / "gpsjam.json").get("days", {})
    index = extras.get("region_index")
    if extras.get("gps_files") and index is not None:
        try:
            import h3

            parsed = {
                day: gpsjam.parse_day(text, index.country_of, h3.cell_to_latlng)
                for day, text in extras["gps_files"].items()
            }
            gps_days = gpsjam.merge_days(gps_days, parsed, today)
        except Exception as exc:  # noqa: BLE001 - GPS data is optional
            print(f"[signals] gpsjam parse failed: {type(exc).__name__}: {exc}")
    (cache_out / "gpsjam.json").write_text(json.dumps({"days": gps_days}, separators=(",", ":")))
    gps = gpsjam.summary(gps_days, today) if gps_days else None
    print(f"[signals] gps days={len(gps_days)} countries={len(gps or {})}")

    # Travel advice history
    history = _load(cache_in / "advisories.json").get("countries", {})
    stamp = today.isoformat()
    for country in snapshot["countries"]:
        us, uk = country.get("advisory") or {}, country.get("advisory_uk") or {}
        text = str(us.get("summary") or "").lower()
        departure = "ordered departure" in text or "authorized departure" in text
        rows = [r for r in history.get(country["iso3"], []) if r[0] != stamp]
        rows.append([stamp, us.get("level"), uk.get("level"), departure])
        history[country["iso3"]] = [
            r for r in rows if (today - date.fromisoformat(r[0])).days <= 180
        ]
    (cache_out / "advisories.json").write_text(
        json.dumps({"countries": history}, separators=(",", ":"))
    )

    # News-classified signs
    news = newswire.merge(
        _load(cache_in / "news.json").get("entries", []),
        extras.get("news_new", []),
        (today - timedelta(days=60)).isoformat(),
    )
    (cache_out / "news.json").write_text(json.dumps({"entries": news}, ensure_ascii=False))

    # Satellite radar
    satellite: dict[str, list[dict]] = {}
    for site in sentinel.SITES:
        result = sentinel.change(extras.get("radar", {}).get(site.key, []))
        if result is None:
            continue
        print(f"[signals] radar {site.key}: x{result['ratio']} last={result['last']}")
        for code in (*site.countries, site.actor):
            satellite.setdefault(code, []).append(
                {"name_ru": site.name_ru, "name_en": site.name_en, **result}
            )

    from geointel.risk import early_signals
    from geointel.risk.warning_signs import apply_persistence

    conflict = {
        c["iso3"]
        for c in snapshot["countries"]
        for key in ("internal_armed_conflict", "interstate_conflict")
        if (c["risks"].get(key) or {}).get("active")
    }
    extra, notes = early_signals.build(
        raw=extras.get("early_raw", {}),
        cache_in=cache_in,
        cache_out=cache_out,
        today=today,
        locate=index.country_of if index is not None else None,
        conflict_countries=conflict,
    )
    print(f"[signals] early sources: {notes}")
    signals = build_signals(
        snapshot,
        today=today,
        gdelt_z=gdelt_z,
        gps=gps,
        advisory_history=history,
        milex=extras.get("milex"),
        hazard_alerts=extras.get("hazard_alerts"),
        satellite=satellite,
        news_entries=news,
        extra_signs=extra,
        status=status,
        generated_at=now,
    )
    trends = early_signals.persistence(
        cache_in / "signals_history.json",
        cache_out / "signals_history.json",
        signals["countries"],
        today,
    )
    by_iso = {c["iso3"]: c for c in snapshot["countries"]}
    for code, entry in list(signals["countries"].items()):
        trend = trends.get(code) or {}
        signals["countries"][code] = apply_persistence(
            by_iso[code], entry, set(trend.get("persistent", [])), trend.get("recent5", {})
        )
        signals["countries"][code]["trend"] = trends.get(code, {})
    signals["dyads"] = dyad_trend
    top = sorted(signals["countries"].items(), key=lambda kv: -kv[1]["max_factor"])[:15]
    print("[signals] top: " + ", ".join(f"{k} x{v['max_factor']:.2f}" for k, v in top))
    for code, item in top[:12]:
        keys = [s["key"] for s in item["signs"] if s["status"] == "active"]
        print(f"[signals]   {code}: {', '.join(keys)}")
    country_signs = {k: v["signs"] for k, v in signals["countries"].items()}
    return signals, {
        "country_signs": country_signs,
        "dyad_trend": dyad_trend,
        "community": extras.get("community"),
    }


def run_backtest_real(out: Path, only: list[str]) -> int:
    import os
    import time

    import httpx

    from geointel.risk import backtest_real
    from geointel.risk.sources import gdelt, sentinel

    cases = [c for c in backtest_real.CASES if not only or c.key in only]
    cache: dict[str, dict] = {}
    results = []
    watch_all = {
        pair for c in cases if c.actor for pair in ((c.actor, c.target), (c.target, c.actor))
    }
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        token = None
        cid, secret = os.environ.get("CDSE_CLIENT_ID"), os.environ.get("CDSE_CLIENT_SECRET")
        if cid and secret:
            try:
                response = client.post(
                    sentinel.TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": cid,
                        "client_secret": secret,
                    },
                )
                response.raise_for_status()
                token = response.json()["access_token"]
            except Exception as exc:  # noqa: BLE001 - radar is optional
                print(f"[backtest] Copernicus token failed: {type(exc).__name__}")
        for case in cases:
            started = time.monotonic()
            days: dict[str, dict] = {}
            if case.monthly:
                for month in backtest_real.months_needed(case):
                    key = f"m{month}"
                    if key not in cache:
                        try:
                            payload = client.get(backtest_real.V1_MONTHLY.format(month=month))
                            payload.raise_for_status()
                            cache[key] = _monthly_days(payload.content, watch_all)
                        except Exception as exc:  # noqa: BLE001 - a missing month is skipped
                            print(f"[backtest] {month}: {type(exc).__name__}")
                            cache[key] = {}
                    days.update(cache[key])
            else:
                for day in backtest_real.days_needed(case):
                    key = day.isoformat()
                    if key not in cache:
                        try:
                            url = gdelt.V1_DAILY.format(day=day.strftime("%Y%m%d"))
                            payload = client.get(url)
                            payload.raise_for_status()
                            text = gdelt.read_export(payload.content)
                            cache[key] = gdelt.aggregate([text], watch_all)
                        except Exception as exc:  # noqa: BLE001 - a missing day is skipped
                            print(f"[backtest] {key}: {type(exc).__name__}")
                            cache[key] = {}
                    if cache[key]:
                        days[key] = cache[key]
            radar = None
            if token and case.sites:
                radar = {}
                event = date.fromisoformat(case.event)
                for site in sentinel.SITES:
                    if site.key not in case.sites:
                        continue
                    try:
                        response = client.post(
                            sentinel.STATS_URL,
                            json=sentinel.request(site, event, days=800),
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        response.raise_for_status()
                        radar[site.key] = sentinel.series(response.json())
                    except Exception as exc:  # noqa: BLE001 - one site failing is fine
                        print(f"[backtest] radar {site.key}: {type(exc).__name__}: {exc}")
            result = backtest_real.evaluate(case, days, radar)
            results.append(result)
            peak = max(result["points"], key=lambda p: p["factor"]) if result["points"] else {}
            print(
                f"[backtest] {case.key}: days={len(days)} lead={result['lead_days']}d "
                f"max_factor={result['max_factor']} brier={result['brier']} "
                f"(base {result['brier_base']}) peak={peak.get('date')} "
                f"{time.monotonic() - started:.0f}s"
            )
            for p in result["points"][-8:]:
                print(f"[backtest]   {p['date']} x{p['factor']} p1m={p['p1m']} {p['signs']}")
    out.parent.mkdir(parents=True, exist_ok=True)
    report = backtest_real.report(results, datetime.now(UTC).isoformat())
    out.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0


def _monthly_days(payload: bytes, watch: set) -> dict[str, dict]:
    """Stream a zipped GDELT monthly file into per-day aggregates."""
    import io
    import zipfile

    from geointel.risk.sources import gdelt

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        with archive.open(archive.namelist()[0]) as handle:
            lines = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
            return gdelt.aggregate_by_day(lines, watch)


def _print_summary(snapshot: dict) -> None:
    for entry in snapshot["event_types"]:
        if not entry["available"]:
            continue
        key = entry["key"]
        ranked = sorted(
            (
                (c["risks"][key]["horizons"]["1y"]["p"], c["iso3"], c["risks"][key]["question"])
                for c in snapshot["countries"]
                if key in c["risks"]
            ),
            reverse=True,
        )
        top = ", ".join(
            f"{iso3} {p:.2f}{'*' if q == 'active_at_end' else ''}" for p, iso3, q in ranked[:12]
        )
        print(f"[summary] {key} ({len(ranked)} countries) 1y top: {top}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m geointel.risk")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch_cmd = sub.add_parser("fetch", help="download public datasets")
    fetch_cmd.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    build_cmd = sub.add_parser("build", help="build the risk snapshot JSON")
    build_cmd.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    build_cmd.add_argument("--out", type=Path, default=Path("data/site/risk.json"))
    build_cmd.add_argument("--previous", type=Path, default=None)
    build_cmd.add_argument("--min-available-types", type=int, default=1)
    bt_cmd = sub.add_parser("backtest-real", help="replay archived data through the signals")
    bt_cmd.add_argument("--out", type=Path, default=Path("data/site/backtest-real.json"))
    bt_cmd.add_argument("--cases", default="")
    acc_cmd = sub.add_parser("accuracy", help="score past scenario forecasts")
    acc_cmd.add_argument("--history-dir", type=Path, default=Path("data/history"))
    acc_cmd.add_argument("--today", type=Path, default=Path("data/site/scenarios.json"))
    acc_cmd.add_argument("--out", type=Path, default=Path("data/site/accuracy.json"))
    notify_cmd = sub.add_parser("notify", help="send the Telegram digest if configured")
    notify_cmd.add_argument("--scenarios", type=Path, default=Path("data/site/scenarios.json"))
    notify_cmd.add_argument("--signals", type=Path, default=Path("data/site/signals.json"))
    notify_cmd.add_argument("--history-dir", type=Path, default=Path("data/history"))
    notify_cmd.add_argument(
        "--signals-history", type=Path, default=Path("data/cache-out/signals_history.json")
    )
    notify_cmd.add_argument("--force", action="store_true", help="send even if nothing changed")
    args = parser.parse_args(argv)

    if args.command == "notify":
        from geointel.risk import notify

        today = datetime.now(UTC).date()
        earlier = sorted(
            p for p in args.history_dir.glob("*-scenarios.json") if p.name[:10] < today.isoformat()
        )
        text = notify.digest(
            notify.load(args.scenarios) or {},
            notify.load(earlier[-1]) if earlier else None,
            notify.load(args.signals) or {},
            (notify.load(args.signals_history) or {}).get("countries", {}),
            today,
            force=args.force,
        )
        if text is None:
            print("[notify] nothing material changed")
            return 0
        print(f"[notify] digest of {len(text)} characters")
        return 0 if notify.send(text) or not args.force else 1

    if args.command == "backtest-real":
        return run_backtest_real(args.out, [c for c in args.cases.split(",") if c])

    if args.command == "accuracy":
        from geointel.risk import accuracy

        today = datetime.now(UTC).date()
        history = accuracy.load_history(args.history_dir)
        if args.today.is_file():
            history[today.isoformat()] = json.loads(args.today.read_text(encoding="utf-8"))
        result = accuracy.build(history, today)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(f"[accuracy] days={result['history_days']} status={result['status']}")
        return 0

    if args.command == "fetch":
        from geointel.risk.fetch import fetch_all

        manifest = fetch_all(args.raw_dir)
        print(json.dumps(manifest, indent=2))
        return 0

    from geointel.risk import backtest
    from geointel.risk.hazards import build_hazard_details
    from geointel.risk.links import build_links
    from geointel.risk.scenarios import build_scenarios
    from geointel.risk.snapshot import build_snapshot

    now = datetime.now(UTC)
    extras: dict = {}
    histories, sources, hazard_events = load_histories(args.raw_dir, now.year, extras)
    previous = None
    if args.previous and args.previous.is_file():
        previous = json.loads(args.previous.read_text())
    snapshot = build_snapshot(
        histories, sources, generated_at=now, previous=previous, extras=extras
    )
    available = sum(1 for t in snapshot["event_types"] if t["available"])
    _print_summary(snapshot)
    from geointel.risk import MODEL_VERSION

    snapshot["model_version"] = MODEL_VERSION
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
    details = build_hazard_details(hazard_events, now)
    (args.out.parent / "hazards.json").write_text(
        json.dumps(details, ensure_ascii=False, separators=(",", ":"))
    )
    signals, scenario_inputs = build_signal_layer(snapshot, extras, sources, now)
    signals["model_version"] = MODEL_VERSION
    from geointel.risk.danger import apply_danger

    histogram = apply_danger(snapshot, signals, extras.get("war_intensity"))
    print(f"[danger] levels: {histogram}")
    for code in ("RUS", "UKR", "USA", "IND", "SDN", "NOR", "ISR", "MEX"):
        d = signals["countries"].get(code, {}).get("danger")
        if d:
            print(
                f"[danger] {code}: {d['level']} (model {d['model_level']}, "
                f"MFA {d['ministry_median']}) "
                + ", ".join(f"{x['risk']}:{x['level']}" for x in d["drivers"][:4])
            )
    (args.out.parent / "signals.json").write_text(
        json.dumps(signals, ensure_ascii=False, separators=(",", ":"))
    )
    (args.out.parent / "backtest.json").write_text(
        json.dumps(backtest.run(), ensure_ascii=False, separators=(",", ":"))
    )
    scenarios = build_scenarios(
        dyads=extras.get("dyads"),
        last_conflict_year=extras.get("ucdp_last_year"),
        active_interstate=extras.get("active_interstate", set()),
        markets=extras.get("markets"),
        milex=extras.get("milex", {}),
        gpr=extras.get("gpr", {}),
        generated_at=now,
        **scenario_inputs,
    )
    for item in scenarios["scenarios"]:
        horizons = " ".join(f"{h}={v['p']:.3f}" for h, v in item["horizons"].items())
        parts = " ".join(f"{c['kind']}={c['annual']:.3f}" for c in item["components"])
        print(
            f"[scenario] {item['key']} {horizons} | {parts} | x{item['indicator_factor']} "
            f"| market={item['market_status']}"
        )
        print(
            "[scenario]   signs: "
            + ", ".join(f"{i['key']}x{i['lr']}" for i in item["indicators"] if i.get("lr"))
        )
        for component in item["components"]:
            if component["kind"] == "history":
                print(f"[scenario]   history: {component['detail_en'][:220]}")
        for candidate in item["market_candidates"]:
            print(
                f"[scenario]   candidate {candidate['p']:.3f} {candidate['end']} "
                f"${candidate['volume']:.0f} {candidate['question'][:100]}"
            )
    links = build_links(
        trade=extras.get("trade"),
        trade_year=extras.get("trade_year"),
        displacement=extras.get("displacement"),
        asylum=extras.get("asylum"),
        profiles=extras.get("profiles"),
        sources=[s for s in sources if s["key"] in ("trade", "unhcr", "eurostat", "milex")],
        generated_at=now,
    )
    for code, value in (extras.get("milex") or {}).items():
        links["countries"].setdefault(code, {})["milex"] = value
    from geointel.risk.network import apply_network
    from geointel.risk.scenarios import CATALOGUE as SCENARIO_CATALOGUE

    apply_network(scenarios, SCENARIO_CATALOGUE, links)
    for item in scenarios["scenarios"]:
        top = ", ".join(
            f"{n['iso3']}:{n['involve']:.2f}/{n['econ']:.2f}" for n in item.get("network", [])[:6]
        )
        print(f"[network] {item['key']}: {top}")
    scenarios["model_version"] = MODEL_VERSION
    (args.out.parent / "scenarios.json").write_text(
        json.dumps(scenarios, ensure_ascii=False, separators=(",", ":"))
    )
    (args.out.parent / "links.json").write_text(
        json.dumps(links, ensure_ascii=False, separators=(",", ":"))
    )
    print(
        f"[links] countries={len(links['countries'])} "
        f"trade={sum(1 for c in links['countries'].values() if 'trade' in c)} "
        f"migration={sum(1 for c in links['countries'].values() if 'migration' in c)}"
    )
    print(
        json.dumps(
            {
                "out": str(args.out),
                "available_types": available,
                "changes": len(snapshot["changes"]),
                "hazard_countries": len(details["countries"]),
                "sources": sources,
            },
            indent=2,
        )
    )
    return 0 if available >= args.min_available_types else 1


if __name__ == "__main__":
    sys.exit(main())
