"""Seed the empty disposable PostgreSQL database for the dashboard browser test."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from geointel.domain.database import SessionLocal, engine
from geointel.domain.models import (
    AnalysisRun,
    Event,
    Evidence,
    Forecast,
    ForecastSignal,
    Indicator,
    Location,
    Source,
)


def moment(month: int) -> datetime:
    return datetime(2020, month, 1, tzinfo=UTC)


def seed() -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "geointel_browser_test":
        raise SystemExit("Use a disposable PostgreSQL database named geointel_browser_test.")
    with SessionLocal.begin() as session:
        for model in (AnalysisRun, Event, Evidence, Forecast, ForecastSignal, Indicator, Location):
            if session.scalar(select(model.id).limit(1)) is not None:
                raise SystemExit("Start with a freshly migrated, empty test database.")

        spain = Location(name="Spain", iso_code="ESP")
        acled = Source(name="ACLED", source_type="operational_events")
        ucdp = Source(name="UCDP", source_type="structured_data")
        session.add_all([spain, acled, ucdp])
        session.flush()
        run = AnalysisRun(
            location_id=spain.id,
            question="Synthetic browser test",
            horizon_months=3,
            status="completed",
            pipeline_version="synthetic-browser-v1",
            provider_config={},
        )
        session.add(run)
        session.flush()
        session.add_all(
            Event(
                id=UUID(int=index),
                analysis_run_id=run.id,
                source_id=acled.id,
                location_id=spain.id,
                source_record_id=f"synthetic-event-{index}",
                occurred_at=moment(1),
                event_type="Synthetic event",
                description="Synthetic browser test",
                confidence="reported",
                provenance={"synthetic_fixture": True, "country": "Spain"},
            )
            for index in range(1, 22)
        )
        session.add(
            Evidence(
                analysis_run_id=run.id,
                source_id=ucdp.id,
                source_record_id="synthetic-ucdp-1",
                title="Synthetic event",
                summary="Synthetic browser test",
                event_date=moment(1),
                retrieved_at=moment(2),
                reliability="reported",
                provenance={
                    "synthetic_fixture": True,
                    "country": "Spain",
                    "dataset": "synthetic GED",
                    "dataset_version": "test-v1",
                    "temporal_role": "annual_historical",
                    "fatalities": {"low": 1, "best": 2, "high": 4},
                },
            )
        )
        session.add(
            Indicator(
                location_id=spain.id,
                name="Synthetic indicator",
                value=0,
                unit="synthetic native unit",
                observed_at=moment(1),
                provenance={"synthetic_fixture": True, "provider": "Synthetic indicator source"},
            )
        )
        for geography, unit in (("Spain", "country"), ("Synthetic district", "admin1")):
            session.add(
                ForecastSignal(
                    analysis_run_id=run.id,
                    location_id=spain.id,
                    provider="Synthetic CAST",
                    source_record_id=f"synthetic-forecast-{unit}",
                    model_name="Synthetic browser model",
                    model_version="test-v1",
                    geographic_unit=unit,
                    source_location=geography,
                    issue_date=moment(2),
                    target_start=moment(3),
                    target_end=moment(5),
                    horizon_months=3,
                    target_variable="Synthetic target",
                    prediction=2.5,
                    unit="native event count",
                    scale="monthly",
                    retrieved_at=moment(2),
                    alignment_status="aligned",
                    alignment_notes=[],
                    provenance={"synthetic_fixture": True},
                )
            )
        session.add(
            Forecast(
                analysis_run_id=run.id,
                created_at=moment(2),
                conflict_type="internal_armed_conflict",
                question=run.question,
                horizon_months=3,
                probability_low=None,
                probability_high=0.25,
                confidence="low",
                rationale="Synthetic browser test",
                evidence_for=[],
                evidence_against=[],
                unknowns=[],
                resolution_criteria=[],
                change_conditions=[],
            )
        )


if __name__ == "__main__":
    seed()
