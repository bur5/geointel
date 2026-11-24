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
    raw_dir: Path, reference_year: int
) -> tuple[dict[EventType, TypeHistory | None], list[dict], list[dict]]:
    """Parse whatever sources were fetched successfully; failures stay unavailable.

    Returns event-type histories, source status records and located hazard events.
    """
    from geointel.risk.sources import coups, fts, gdacs, ncei_tsunami, ucdp_acd, usgs, worldbank

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

    loaders: list[tuple[str, str, Callable[[Path], None]]] = [
        ("ucdp_acd", ucdp_acd.SOURCE, ucdp),
        ("coups", coups.SOURCE, coup),
        ("usgs", usgs.SOURCE, quakes),
        ("gdacs", gdacs.SOURCE, gdacs_alerts),
        ("tsunami", ncei_tsunami.SOURCE, tsunamis),
        ("worldbank", worldbank.SOURCE, economy),
        ("fts", fts.SOURCE, humanitarian),
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
    from geointel.risk.snapshot import build_snapshot

    now = datetime.now(UTC)
    histories, sources, hazard_events = load_histories(args.raw_dir, now.year)
    previous = None
    if args.previous and args.previous.is_file():
        previous = json.loads(args.previous.read_text())
    snapshot = build_snapshot(histories, sources, generated_at=now, previous=previous)
    available = sum(1 for t in snapshot["event_types"] if t["available"])
    _print_summary(snapshot)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
    details = build_hazard_details(hazard_events, now)
    (args.out.parent / "hazards.json").write_text(
        json.dumps(details, ensure_ascii=False, separators=(",", ":"))
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
