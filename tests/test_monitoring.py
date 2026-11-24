from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from geointel.connectors.base import DisabledConnector
from geointel.domain.models import Alert, AnalysisRun, DetectedChange, Forecast, MonitoringRun
from geointel.monitoring import AlertEngine, ChangeDetector, MonitoringService, is_due, next_due
from geointel.pipeline.service import AnalysisPipeline
from geointel.providers.base import ModelRouter
from geointel.providers.offline import OfflineModel


def service(session, connectors=None):
    model = OfflineModel()
    return MonitoringService(
        session,
        lambda: AnalysisPipeline(
            session,
            ModelRouter(model, model, model),
            connectors or [DisabledConnector(x) for x in ("UCDP", "ACLED", "VIEWS", "CAST")],
        ),
    )


def test_watchlist_target_cadence_due_and_disable(session):
    svc = service(session)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    watchlist = svc.create_watchlist("Synthetic watchlist", metadata={"fixture": True})
    target = svc.add_target(watchlist, "SYN", "Synthetic Country", "every_6_hours", now=now)
    assert target.target_type == "country" and is_due(target, now)
    target.next_due_at = next_due(target.cadence, now)
    session.commit()
    assert not is_due(target, now + timedelta(hours=5))
    assert is_due(target, now + timedelta(hours=6))
    svc.disable_target(target)
    assert not is_due(target, now + timedelta(days=1))
    with pytest.raises(ValueError):
        svc.add_target(watchlist, "BAD", "Bad", "every_5_minutes")
    with pytest.raises(ValueError):
        svc.create_watchlist("x" * 201)


def test_baseline_then_identical_uses_normal_pipeline_without_alert(session):
    svc = service(session)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    watchlist = svc.create_watchlist("Synthetic Spain control")
    target = svc.add_target(watchlist, "SYN-ES", "Synthetic Spain", now=now)
    first = svc.run_target(target, now=now)
    assert first.status == "completed" and first.baseline_established
    assert (
        first.analysis_run_id
        and session.get(AnalysisRun, first.analysis_run_id).status == "completed"
    )
    assert len(session.get(AnalysisRun, first.analysis_run_id).forecasts) == 4
    second = svc.run_target(target, now=now + timedelta(days=1))
    assert second.status == "completed" and not second.baseline_established
    assert second.previous_analysis_run_id == first.analysis_run_id
    assert session.scalars(select(Alert)).all() == []
    assert session.scalars(select(DetectedChange)).all() == []
    assert target.next_due_at.tzinfo is not None


def test_incompatible_horizon_establishes_new_baseline(session):
    svc = service(session)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    target = svc.add_target(svc.create_watchlist("Synthetic"), "SYN", "Synthetic", now=now)
    svc.run_target(target, now=now)
    target.horizon_months = 6
    session.commit()
    run = svc.run_target(target, now=now + timedelta(days=1))
    assert run.baseline_established and run.previous_analysis_run_id is None


def test_failed_analysis_is_audited(session):
    class Broken:
        def run(self, request):
            raise RuntimeError("synthetic failure secretless")

    svc = MonitoringService(session, Broken)
    target = svc.add_target(svc.create_watchlist("Synthetic"), "SYN", "Synthetic")
    run = svc.run_target(target)
    assert run.status == "failed" and "synthetic failure" in run.error_reason
    assert run.analysis_run_id is None


def state(**updates):
    value = {
        "forecasts": {},
        "changed_categories": [],
        "event_ids": [],
        "event_sources": [],
        "signals": {},
        "signal_providers": [],
        "disagreements": [],
        "source_health": {
            x: "available" for x in ("UCDP", "ACLED", "VIEWS", "CAST", "Strategic Knowledge")
        },
        "uncertainty": {},
        "strategic_context": [],
        "red_team": {},
        "recency": "stale",
    }
    value.update(updates)
    return value


def test_change_detector_metamorphic_guardrails():
    detector = ChangeDetector()
    baseline = state()
    one = detector.detect(baseline, state(event_ids=["ACLED:1"], event_sources=["ACLED"]))
    assert one[0]["change_type"] == "new_operational_events" and not one[0]["material"]
    duplicate = detector.detect(state(event_ids=["ACLED:1"]), state(event_ids=["ACLED:1"]))
    assert not any(x["change_type"] == "new_operational_events" for x in duplicate)
    many = detector.detect(baseline, state(event_ids=["A:1", "B:2"], event_sources=["A", "B"]))
    assert next(x for x in many if x["change_type"] == "new_operational_events")["material"]
    strategic = detector.detect(baseline, state(strategic_context=["claim-1"]))
    assert (
        strategic[0]["change_type"] == "strategic_context_change" and not strategic[0]["material"]
    )
    outage = detector.detect(
        baseline, state(source_health={**baseline["source_health"], "ACLED": "failed"})
    )
    assert not next(x for x in outage if x["change_type"] == "source_availability_change")[
        "material"
    ]
    multi = detector.detect(
        baseline,
        state(source_health={**baseline["source_health"], "ACLED": "failed", "VIEWS": "failed"}),
    )
    assert next(x for x in multi if x["change_type"] == "source_availability_change")["material"]
    recency = detector.detect(baseline, state(recency="current_corroborated"))
    assert next(x for x in recency if x["change_type"] == "data_recency_change")["material"]


def test_alert_provenance_deduplication_and_resolution(session):
    svc = service(session)
    target = svc.add_target(svc.create_watchlist("Synthetic"), "SYN", "Synthetic")
    base = MonitoringRun(
        target_id=target.id,
        status="completed",
        trigger_type="manual",
        baseline_established=False,
        source_availability={},
        run_metadata={},
    )
    session.add(base)
    session.flush()
    change = DetectedChange(
        monitoring_run_id=base.id,
        change_type="forecast_change",
        previous_state={"value": "low"},
        current_state={"value": "changed"},
        affected_categories=["interstate_armed_conflict"],
        source_references=["synthetic:1"],
        severity="material",
        material=True,
        explanation="Structured forecast changed.",
        provenance={
            "previous_analysis_run_id": "synthetic-old",
            "current_analysis_run_id": "synthetic-new",
        },
    )
    session.add(change)
    session.flush()
    engine = AlertEngine()
    first = engine.evaluate(
        session, target, base, [change], {"uncertainty": ["review"]}, {"ACLED": "missing"}
    )
    session.flush()
    second = engine.evaluate(session, target, base, [change], {}, {"ACLED": "missing"})
    assert first.id == second.id and first.provenance["change_ids"] == [str(change.id)]
    assert first.counterevidence and first.affected_categories == ["interstate_armed_conflict"]
    engine.resolve(session, first)
    session.commit()
    assert first.status == "resolved" and first.resolved_at
    assert session.scalar(select(Alert).where(Alert.id == first.id)) is not None


def test_forecast_remains_immutable_during_monitoring(session):
    svc = service(session)
    target = svc.add_target(svc.create_watchlist("Synthetic"), "SYN", "Synthetic")
    run = svc.run_target(target)
    forecast = session.scalar(
        select(Forecast).where(Forecast.analysis_run_id == run.analysis_run_id)
    )
    forecast.rationale = "mutation"
    with pytest.raises(ValueError):
        session.commit()


def test_cli_create_run_due_and_alert_inspection(tmp_path):
    import json
    import os
    import subprocess
    import sys

    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'monitoring.db'}",
        "PYTHONPATH": str(__import__("pathlib").Path(__file__).parents[1] / "src"),
    }

    def command(*args):
        result = subprocess.run(
            [sys.executable, "-m", "geointel.monitoring", *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return json.loads(result.stdout)

    watchlist = command("create-watchlist", "Synthetic CLI")
    target = command("add-target", watchlist["watchlist_id"], "SYN-CLI", "Synthetic CLI Country")
    first = command("run-target", target["target_id"])
    assert first["status"] == "completed" and first["baseline_established"]
    # Manual run advanced next_due_at, so run-due deterministically finds nothing.
    assert command("run-due") == []
    assert command("list-alerts") == []


def test_legacy_rollout_uses_first_v1_eligibility_baseline(session):
    svc = service(session)
    target = svc.add_target(svc.create_watchlist("Rollout"), "ESP", "Spain")
    legacy = svc.run_target(target)
    legacy.analysis_run.pipeline_version = "0.1.7"
    metadata = dict(legacy.analysis_run.collection_metadata)
    metadata.pop("collection_coverage")
    metadata["connector_outcomes"] = []
    legacy.analysis_run.collection_metadata = metadata
    session.commit()

    initial = svc.run_target(target)
    assert initial.previous_analysis_run_id == legacy.analysis_run_id
    assert initial.baseline_established
    assert any(c.change_type == "source_availability_change" for c in initial.changes)
    assert all(not c.material for c in initial.changes)
    next_run = svc.run_target(target)
    assert next_run.previous_analysis_run_id == initial.analysis_run_id
    assert not next_run.baseline_established
    assert session.scalars(select(Alert)).all() == []


def test_unchanged_provider_cannot_corroborate_new_events():
    detector = ChangeDetector()
    before = state(assessment_records={"event_ids": ["B:old"]})
    after = state(
        assessment_records={"event_ids": ["B:old", "A:1", "A:2"], "recency": "current_corroborated"}
    )
    changes = detector.detect(before, after)
    assert {c["change_type"] for c in changes} == {"new_operational_events", "data_recency_change"}
    assert all(not c["material"] for c in changes)
    after["assessment_records"]["event_ids"].append("B:new")
    assert all(c["material"] for c in detector.detect(before, after))


def test_operational_health_materiality_excludes_historical_health():
    detector = ChangeDetector()
    before = state(has_history=True, assessment_records={})
    outage = state(
        has_history=True,
        assessment_records={},
        source_health=before["source_health"] | {"ACLED": "failed", "VIEWS": "failed"},
    )
    (change,) = detector.detect(before, outage)
    assert change["material"]
    assert "UCDP" not in change["current_state"]["value"]
    historical_outage = outage | {"source_health": outage["source_health"] | {"UCDP": "failed"}}
    (change,) = detector.detect(outage, historical_outage)
    assert not change["material"]
    assert change["current_state"]["value"]["UCDP"] == "failed"
