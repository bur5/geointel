"""Deterministic scheduler-ready monitoring, change detection, and alert decisions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from geointel.domain.models import (
    Alert,
    AnalysisRun,
    DetectedChange,
    MonitoringRun,
    Watchlist,
    WatchlistTarget,
)
from geointel.domain.schemas import AnalysisRequest

CADENCES = {
    "hourly": timedelta(hours=1),
    "every_6_hours": timedelta(hours=6),
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
}
SOURCE_NAMES = ("UCDP", "ACLED", "VIEWS", "CAST", "Strategic Knowledge")
CHANGE_TYPES = (
    "forecast_change",
    "new_operational_events",
    "predictive_signal_change",
    "source_disagreement_change",
    "source_availability_change",
    "uncertainty_change",
    "strategic_context_change",
    "red_team_change",
    "data_recency_change",
)


def utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def now_utc() -> datetime:
    return datetime.now(UTC)


def next_due(cadence: str, after: datetime) -> datetime:
    if cadence not in CADENCES:
        raise ValueError(f"unsupported cadence: {cadence}; minimum supported interval is one hour")
    return utc(after) + CADENCES[cadence]


def is_due(target: WatchlistTarget, now: datetime) -> bool:
    return bool(target.enabled and target.watchlist.enabled and utc(target.next_due_at) <= utc(now))


class ChangeDetector:
    """Compares structured state; prose and timestamps are deliberately excluded."""

    def detect(self, previous: dict, current: dict) -> list[dict]:
        changes: list[dict] = []
        self._compare_map(changes, "forecast_change", previous, current, "forecasts", True)
        old_events, new_events = set(previous["event_ids"]), set(current["event_ids"])
        added = sorted(new_events - old_events)
        if added:
            material = len(added) >= 2 and len(current.get("event_sources", [])) >= 2
            self._add(
                changes,
                "new_operational_events",
                sorted(old_events),
                added,
                material,
                (
                    "New unique operational event identities were observed; independence is "
                    "required for materiality."
                ),
                [],
                added,
            )
        self._compare_map(
            changes,
            "predictive_signal_change",
            previous,
            current,
            "signals",
            len(current.get("signal_providers", [])) >= 2,
        )
        self._compare_map(
            changes, "source_disagreement_change", previous, current, "disagreements", False
        )
        old_health, new_health = previous["source_health"], current["source_health"]
        if old_health != new_health:
            failed = [k for k, v in new_health.items() if v in {"failed", "missing"}]
            self._add(
                changes,
                "source_availability_change",
                old_health,
                new_health,
                len(failed) >= 2,
                "Source health changed; this is data quality, not geopolitical escalation.",
                [],
                failed,
            )
        self._compare_map(changes, "uncertainty_change", previous, current, "uncertainty", True)
        self._compare_map(
            changes, "strategic_context_change", previous, current, "strategic_context", False
        )
        self._compare_map(changes, "red_team_change", previous, current, "red_team", False)
        self._compare_map(
            changes,
            "data_recency_change",
            previous,
            current,
            "recency",
            current.get("recency") == "current_corroborated",
        )
        return changes

    def _compare_map(self, changes, kind, previous, current, field, material):
        if previous.get(field) != current.get(field):
            categories = (
                sorted(current.get("changed_categories", [])) if kind == "forecast_change" else []
            )
            self._add(
                changes,
                kind,
                previous.get(field),
                current.get(field),
                material,
                f"Structured {field.replace('_', ' ')} state changed.",
                categories,
                [],
            )

    @staticmethod
    def _add(changes, kind, before, after, material, explanation, categories, sources):
        changes.append(
            {
                "change_type": kind,
                "previous_state": {"value": before},
                "current_state": {"value": after},
                "affected_categories": categories,
                "source_references": sources,
                "severity": "material" if material else "informational",
                "material": material,
                "explanation": explanation,
            }
        )


class AlertEngine:
    """Applies conservative guardrails and append-only alert lifecycle semantics."""

    def evaluate(
        self,
        session: Session,
        target: WatchlistTarget,
        run: MonitoringRun,
        changes: list[DetectedChange],
        red_team: dict,
        source_health: dict,
    ) -> Alert | None:
        material = [
            c for c in changes if c.material and c.change_type != "strategic_context_change"
        ]
        if run.baseline_established or not material:
            return None
        fingerprint = [
            {
                "type": c.change_type,
                "state": c.current_state,
                "categories": sorted(c.affected_categories),
            }
            for c in material
        ]
        key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
        existing = session.scalar(
            select(Alert).where(Alert.target_id == target.id, Alert.deduplication_key == key)
        )
        now = now_utc()
        if existing:
            existing.last_observed_at = now
            return existing
        missing = sorted(k for k, value in source_health.items() if value != "available")
        categories = sorted({x for c in material for x in c.affected_categories})
        guardrails = [
            "Predictive signals are not facts and strategic interpretation is not evidence.",
            "Duplicate and isolated events do not independently justify a generalized alert.",
            "Missing sources and geographic/horizon mismatch can increase uncertainty.",
            *[str(x) for values in red_team.values() if isinstance(values, list) for x in values],
        ]
        alert = Alert(
            target_id=target.id,
            monitoring_run_id=run.id,
            deduplication_key=key,
            status="open",
            priority="notable",
            what_changed=[c.explanation for c in material],
            analytical_significance=(
                "A deterministic materiality rule was met; human review is required."
            ),
            evidence=[{"change_id": str(c.id), "provenance": c.provenance} for c in material],
            counterevidence=guardrails,
            missing_or_disagreeing_sources=missing,
            affected_categories=categories,
            confirmation_or_reversal=[
                "Seek current, independent corroboration and reassess on the next comparable run."
            ],
            guardrails=guardrails,
            provenance={
                "monitoring_run_id": str(run.id),
                "analysis_run_id": str(run.analysis_run_id),
                "change_ids": [str(c.id) for c in material],
            },
            first_detected_at=now,
            last_observed_at=now,
        )
        session.add(alert)
        return alert

    @staticmethod
    def resolve(session: Session, alert: Alert, at: datetime | None = None) -> None:
        alert.status = "resolved"
        alert.resolved_at = utc(at or now_utc())
        alert.last_observed_at = alert.resolved_at
        session.flush()


class MonitoringService:
    def __init__(self, session: Session, pipeline_factory: Callable[[], object]):
        self.session = session
        self.pipeline_factory = pipeline_factory
        self.detector = ChangeDetector()
        self.alert_engine = AlertEngine()

    def create_watchlist(
        self, name: str, description: str = "", metadata: dict | None = None
    ) -> Watchlist:
        self._bounded(name, 200, "name")
        self._bounded(description, 4000, "description", allow_empty=True)
        self._metadata(metadata)
        item = Watchlist(name=name, description=description, watchlist_metadata=metadata or {})
        self.session.add(item)
        self.session.commit()
        return item

    def add_target(
        self,
        watchlist: Watchlist,
        geography_id: str,
        display_name: str,
        cadence: str = "daily",
        horizon_months: int = 12,
        question: str | None = None,
        metadata: dict | None = None,
        now: datetime | None = None,
    ) -> WatchlistTarget:
        if cadence not in CADENCES:
            next_due(cadence, now or now_utc())
        if not 1 <= horizon_months <= 120:
            raise ValueError("horizon_months must be between 1 and 120")
        for value, size, label in (
            (geography_id, 120, "geography_id"),
            (display_name, 200, "display_name"),
        ):
            self._bounded(value, size, label)
        q = question or (
            f"Analyze material changes in the four GEOINTEL conflict categories for {display_name} "
            f"over the next {horizon_months} months."
        )
        self._bounded(q, 4000, "question")
        self._metadata(metadata)
        when = utc(now or now_utc())
        target = WatchlistTarget(
            watchlist_id=watchlist.id,
            target_type="country",
            geography_id=geography_id,
            display_name=display_name,
            enabled=True,
            cadence=cadence,
            horizon_months=horizon_months,
            question=q,
            next_due_at=when,
            target_metadata=metadata or {},
        )
        self.session.add(target)
        self.session.commit()
        return target

    def disable_target(self, target: WatchlistTarget) -> None:
        target.enabled = False
        target.updated_at = now_utc()
        self.session.commit()

    def list_targets(self, watchlist_id=None) -> list[WatchlistTarget]:
        query = select(WatchlistTarget).order_by(WatchlistTarget.created_at, WatchlistTarget.id)
        if watchlist_id:
            query = query.where(WatchlistTarget.watchlist_id == watchlist_id)
        return list(self.session.scalars(query))

    def targets_due(self, now: datetime | None = None) -> list[WatchlistTarget]:
        when = utc(now or now_utc())
        candidates = self.session.scalars(
            select(WatchlistTarget)
            .where(WatchlistTarget.enabled.is_(True))
            .order_by(WatchlistTarget.next_due_at, WatchlistTarget.id)
        ).all()
        return [x for x in candidates if is_due(x, when)]

    def run_due_targets(self, now: datetime | None = None) -> list[MonitoringRun]:
        when = utc(now or now_utc())
        return [self.run_target(x, trigger_type="due", now=when) for x in self.targets_due(when)]

    def run_target(
        self, target: WatchlistTarget, trigger_type: str = "manual", now: datetime | None = None
    ) -> MonitoringRun:
        when = utc(now or now_utc())
        attempt = MonitoringRun(
            target_id=target.id,
            status="running",
            trigger_type=trigger_type,
            started_at=when,
            source_availability={},
            run_metadata={},
        )
        self.session.add(attempt)
        self.session.commit()
        try:
            previous = self._previous_comparable(target)
            analysis = self.pipeline_factory().run(
                AnalysisRequest(
                    location=target.display_name,
                    question=target.question,
                    horizon_months=target.horizon_months,
                )
            )
            attempt.analysis_run_id = analysis.id
            attempt.previous_monitoring_run_id = previous.id if previous else None
            attempt.previous_analysis_run_id = previous.analysis_run_id if previous else None
            attempt.baseline_established = previous is None
            attempt.source_availability = self._source_health(analysis)
            if previous:
                before, current = self._snapshot(previous.analysis_run), self._snapshot(analysis)
                for data in self.detector.detect(before, current):
                    change = DetectedChange(
                        monitoring_run_id=attempt.id,
                        **data,
                        provenance={
                            "previous_analysis_run_id": str(previous.analysis_run_id),
                            "current_analysis_run_id": str(analysis.id),
                        },
                    )
                    self.session.add(change)
                    self.session.flush()
            attempt.status = "completed"
            attempt.completed_at = now_utc()
            target.last_successful_run_at = attempt.completed_at
            target.next_due_at = next_due(target.cadence, when)
            self.session.flush()
            self.alert_engine.evaluate(
                self.session,
                target,
                attempt,
                list(attempt.changes),
                analysis.red_team_output or {},
                attempt.source_availability,
            )
            self.session.commit()
            self.session.refresh(attempt)
            return attempt
        except Exception as exc:
            self.session.rollback()
            attempt = self.session.get(MonitoringRun, attempt.id)
            attempt.status = "failed"
            attempt.completed_at = now_utc()
            attempt.error_reason = " ".join(str(exc).split())[:500] or type(exc).__name__
            self.session.commit()
            return attempt

    def _previous_comparable(self, target):
        runs = self.session.scalars(
            select(MonitoringRun)
            .where(
                MonitoringRun.target_id == target.id,
                MonitoringRun.status == "completed",
                MonitoringRun.analysis_run_id.is_not(None),
            )
            .order_by(MonitoringRun.started_at.desc())
        ).all()
        for run in runs:
            analysis = run.analysis_run
            if (
                analysis
                and analysis.status == "completed"
                and analysis.horizon_months == target.horizon_months
                and analysis.pipeline_version == "0.1.0"
                and len(analysis.forecasts) == 4
            ):
                return run
        return None

    @staticmethod
    def _source_health(run: AnalysisRun) -> dict:
        health = {name: "missing" for name in SOURCE_NAMES}
        for item in run.collection_metadata.get("connector_outcomes", []):
            health[item["connector"]] = (
                "available" if item["status"] == "succeeded" else item["status"]
            )
        health["Strategic Knowledge"] = "available" if run.strategic_analyses else "missing"
        return health

    @staticmethod
    def _snapshot(run: AnalysisRun) -> dict:
        forecasts = {
            f.conflict_type: {
                "confidence": f.confidence,
                "probability_low": f.probability_low,
                "probability_high": f.probability_high,
                "evidence_for": sorted(f.evidence_for),
                "evidence_against": sorted(f.evidence_against),
                "unknowns": sorted(f.unknowns),
            }
            for f in run.forecasts
        }
        signals = {
            f"{s.provider}:{s.source_record_id}": {
                "prediction": s.prediction,
                "alignment_status": s.alignment_status,
                "target_variable": s.target_variable,
            }
            for s in run.forecast_signals
        }
        outcomes = MonitoringService._source_health(run)
        disagreements = sorted((run.analyst_output or {}).get("source_disagreements", []))
        strategic = sorted(str(x) for a in run.strategic_analyses for x in a.retrieved_claim_ids)
        event_ids = sorted(f"{e.source_id}:{e.source_record_id}" for e in run.events)
        event_sources = sorted({str(e.source_id) for e in run.events})
        recencies = [e.provenance.get("alignment_status") for e in run.events]
        recency = (
            "current_corroborated"
            if recencies.count("aligned") + recencies.count("current_window") >= 2
            else (sorted(set(x for x in recencies if x)) or ["none"])[0]
        )
        return {
            "forecasts": forecasts,
            "changed_categories": list(forecasts),
            "event_ids": event_ids,
            "event_sources": event_sources,
            "signals": signals,
            "signal_providers": sorted({s.provider for s in run.forecast_signals}),
            "disagreements": disagreements,
            "source_health": outcomes,
            "uncertainty": {k: v["confidence"] for k, v in forecasts.items()},
            "strategic_context": strategic,
            "red_team": run.red_team_output or {},
            "recency": recency,
        }

    @staticmethod
    def _bounded(value: str, maximum: int, label: str, allow_empty: bool = False) -> None:
        if (not value and not allow_empty) or len(value) > maximum or "\x00" in value:
            raise ValueError(f"invalid {label}")

    @staticmethod
    def _metadata(value: dict | None) -> None:
        if value is not None and (not isinstance(value, dict) or len(json.dumps(value)) > 10_000):
            raise ValueError("metadata must be a JSON object no larger than 10 KB")
