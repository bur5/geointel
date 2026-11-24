"""Command line: ``python -m geointel.risk fetch|build``."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from geointel.risk.model import TypeHistory
from geointel.risk.taxonomy import EventType


def load_histories(raw_dir: Path, reference_year: int) -> tuple[dict, list[dict]]:
    """Parse whatever sources were fetched successfully; failures stay unavailable."""
    from geointel.risk.sources import coups, ucdp_acd, usgs

    manifest_path = raw_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    histories: dict[EventType, TypeHistory | None] = {}
    sources = []

    def record(key: str, name: str, error: str | None = None) -> None:
        info = manifest.get(key, {})
        sources.append(
            {
                "key": key,
                "name": name,
                "url": info.get("url"),
                "version": info.get("version"),
                "retrieved_at": info.get("retrieved_at"),
                "status": "ok" if error is None and info.get("status") == "ok" else "failed",
                "error": error or ("; ".join(info.get("errors", [])) or None),
            }
        )

    def ok(key: str) -> Path | None:
        info = manifest.get(key, {})
        path = raw_dir / info.get("file", "")
        return path if info.get("status") == "ok" and path.is_file() else None

    if path := ok("ucdp_acd"):
        try:
            version = manifest["ucdp_acd"].get("version")
            internal, interstate = ucdp_acd.parse(
                ucdp_acd.read_csv_bytes(path.read_bytes()), version=version
            )
            histories[EventType.INTERNAL_ARMED_CONFLICT] = internal
            histories[EventType.INTERSTATE_CONFLICT] = interstate
            record("ucdp_acd", ucdp_acd.SOURCE)
        except Exception as exc:  # noqa: BLE001
            record("ucdp_acd", ucdp_acd.SOURCE, f"parse error: {exc}")
    else:
        record("ucdp_acd", ucdp_acd.SOURCE)
    if path := ok("coups"):
        try:
            text = path.read_bytes().decode("utf-8", errors="replace")
            histories[EventType.COUP_ATTEMPT] = coups.parse(text, reference_year)
            record("coups", coups.SOURCE)
        except Exception as exc:  # noqa: BLE001
            record("coups", coups.SOURCE, f"parse error: {exc}")
    else:
        record("coups", coups.SOURCE)
    if path := ok("usgs"):
        try:
            histories[EventType.MAJOR_EARTHQUAKE] = usgs.parse(path.read_text(), reference_year)
            record("usgs", usgs.SOURCE)
        except Exception as exc:  # noqa: BLE001
            record("usgs", usgs.SOURCE, f"parse error: {exc}")
    else:
        record("usgs", usgs.SOURCE)
    return histories, sources


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

    from geointel.risk.snapshot import build_snapshot

    now = datetime.now(UTC)
    histories, sources = load_histories(args.raw_dir, now.year)
    previous = None
    if args.previous and args.previous.is_file():
        previous = json.loads(args.previous.read_text())
    snapshot = build_snapshot(histories, sources, generated_at=now, previous=previous)
    available = sum(1 for t in snapshot["event_types"] if t["available"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
    print(
        json.dumps(
            {
                "out": str(args.out),
                "available_types": available,
                "changes": len(snapshot["changes"]),
                "sources": sources,
            },
            indent=2,
        )
    )
    return 0 if available >= args.min_available_types else 1


if __name__ == "__main__":
    sys.exit(main())
