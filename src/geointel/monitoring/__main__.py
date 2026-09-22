"""Operator CLI. Configuration values are inert data and never commands."""

import argparse
import json
import uuid

from sqlalchemy import select

from geointel.api.app import connectors, router
from geointel.domain.database import SessionLocal, create_tables
from geointel.domain.models import Alert, Watchlist, WatchlistTarget
from geointel.monitoring.service import CADENCES, MonitoringService
from geointel.pipeline.service import AnalysisPipeline


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m geointel.monitoring")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-watchlist")
    create.add_argument("name")
    create.add_argument("--description", default="")
    add = sub.add_parser("add-target")
    add.add_argument("watchlist_id")
    add.add_argument("geography_id")
    add.add_argument("display_name")
    add.add_argument("--cadence", choices=CADENCES, default="daily")
    add.add_argument("--horizon-months", type=int, default=12)
    add.add_argument("--question")
    one = sub.add_parser("run-target")
    one.add_argument("target_id")
    sub.add_parser("run-due")
    sub.add_parser("list-alerts")
    args = parser.parse_args()
    create_tables()
    with SessionLocal() as session:
        service = MonitoringService(
            session, lambda: AnalysisPipeline(session, router(), connectors())
        )
        if args.command == "create-watchlist":
            item = service.create_watchlist(args.name, args.description)
            result = {"watchlist_id": str(item.id)}
        elif args.command == "add-target":
            watchlist = session.get(Watchlist, uuid.UUID(args.watchlist_id))
            if not watchlist:
                parser.error("watchlist not found")
            item = service.add_target(
                watchlist,
                args.geography_id,
                args.display_name,
                args.cadence,
                args.horizon_months,
                args.question,
            )
            result = {"target_id": str(item.id), "next_due_at": item.next_due_at.isoformat()}
        elif args.command == "run-target":
            target = session.get(WatchlistTarget, uuid.UUID(args.target_id))
            if not target:
                parser.error("target not found")
            item = service.run_target(target)
            result = present_run(item)
        elif args.command == "run-due":
            result = [present_run(item) for item in service.run_due_targets()]
        else:
            result = [
                {
                    "id": str(x.id),
                    "target_id": str(x.target_id),
                    "status": x.status,
                    "priority": x.priority,
                    "what_changed": x.what_changed,
                    "first_detected_at": x.first_detected_at.isoformat(),
                    "resolved_at": x.resolved_at.isoformat() if x.resolved_at else None,
                }
                for x in session.scalars(select(Alert).order_by(Alert.first_detected_at))
            ]
        print(json.dumps(result, sort_keys=True))


def present_run(item):
    return {
        "monitoring_run_id": str(item.id),
        "analysis_run_id": str(item.analysis_run_id) if item.analysis_run_id else None,
        "status": item.status,
        "baseline_established": item.baseline_established,
        "previous_analysis_run_id": str(item.previous_analysis_run_id)
        if item.previous_analysis_run_id
        else None,
        "source_availability": item.source_availability,
    }


if __name__ == "__main__":
    main()
