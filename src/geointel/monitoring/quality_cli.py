"""Operator entry point for one read-only source health report."""

import argparse
import json
from datetime import UTC, datetime
from uuid import UUID

from geointel.domain.database import SessionLocal
from geointel.monitoring.data_quality import DEFAULT_FRESHNESS_DAYS, source_health_report


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m geointel.monitoring.quality_cli")
    parser.add_argument("analysis_run_id", type=UUID)
    parser.add_argument("--as-of", type=datetime.fromisoformat, help="ISO 8601 with UTC offset")
    for source in DEFAULT_FRESHNESS_DAYS:
        parser.add_argument(f"--{source.lower()}-freshness-days", type=int)
    args = parser.parse_args()
    overrides = {
        source: days
        for source in DEFAULT_FRESHNESS_DAYS
        if (days := getattr(args, f"{source.lower()}_freshness_days")) is not None
    }
    with SessionLocal() as session:
        try:
            report = source_health_report(
                session,
                args.analysis_run_id,
                as_of=args.as_of or datetime.now(UTC),
                freshness_days=overrides,
            )
        except ValueError as exc:
            parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
