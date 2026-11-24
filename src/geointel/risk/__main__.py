"""Command line: ``python -m geointel.risk fetch|build``."""

import argparse
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
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
        migration,
        ncei_tsunami,
        outlook,
        polymarket,
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
        extras["active_interstate"] = {
            code
            for code, years in interstate.years_with_event.items()
            if interstate.end_year in years
        }

    def coup(path: Path) -> None:
        text = path.read_bytes().decode("utf-8", errors="replace")
        histories[EventType.COUP_ATTEMPT] = coups.parse(text, reference_year)

    def quakes(path: Path) -> None:
        text = path.read_text()
        histories[EventType.MAJOR_EARTHQUAKE] = usgs.parse(text, reference_year)
        hazard_events.extend(usgs.events(text))

    def gdacs_alerts(path: Path) -> None:
        events = gdacs.normalize_all(json.loads(path.read_text()).get("features", []))
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

    def admin_regions(path: Path) -> None:
        from geointel.risk.regions import RegionIndex, annotate

        annotate(hazard_events, RegionIndex.from_bytes(path.read_bytes()))

    loaders: list[tuple[str, str, Callable[[Path], None]]] = [
        ("ucdp_acd", ucdp_acd.SOURCE, ucdp),
        ("coups", coups.SOURCE, coup),
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
    args = parser.parse_args(argv)

    if args.command == "fetch":
        from geointel.risk.fetch import fetch_all

        manifest = fetch_all(args.raw_dir)
        print(json.dumps(manifest, indent=2))
        return 0

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
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
    details = build_hazard_details(hazard_events, now)
    (args.out.parent / "hazards.json").write_text(
        json.dumps(details, ensure_ascii=False, separators=(",", ":"))
    )
    scenarios = build_scenarios(
        dyads=extras.get("dyads"),
        last_conflict_year=extras.get("ucdp_last_year"),
        active_interstate=extras.get("active_interstate", set()),
        markets=extras.get("markets"),
        milex=extras.get("milex", {}),
        gpr=extras.get("gpr", {}),
        generated_at=now,
    )
    for item in scenarios["scenarios"]:
        horizons = " ".join(f"{h}={v['p']:.3f}" for h, v in item["horizons"].items())
        parts = " ".join(f"{c['kind']}={c['annual']:.3f}" for c in item["components"])
        print(
            f"[scenario] {item['key']} {horizons} | {parts} | x{item['indicator_factor']} "
            f"| market={item['market_status']}"
        )
        for candidate in item["market_candidates"]:
            print(
                f"[scenario]   candidate {candidate['p']:.3f} {candidate['end']} "
                f"${candidate['volume']:.0f} {candidate['question'][:100]}"
            )
    (args.out.parent / "scenarios.json").write_text(
        json.dumps(scenarios, ensure_ascii=False, separators=(",", ":"))
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
