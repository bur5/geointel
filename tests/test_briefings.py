import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from geointel.briefings import BriefingRequest, BriefingType, generate_briefing
from geointel.domain.models import (
    AnalysisRun,
    Event,
    Evidence,
    Forecast,
    ForecastSignal,
    Indicator,
    KnowledgeSection,
    KnowledgeWork,
    Location,
    Scenario,
    Source,
    StrategicAnalysis,
    StrategicClaim,
)

CUTOFF = date(2024, 6, 30)
EVENT = datetime(2024, 6, 26, tzinfo=UTC)
PUBLISHED = EVENT + timedelta(days=1)
INGESTED = EVENT + timedelta(days=2)
COMPLETED = INGESTED + timedelta(hours=1)
LOCATION = UUID(int=1)
OTHER = UUID(int=2)
RUN = UUID(int=3)
SOURCE = UUID(int=4)


def report(session, kind=BriefingType.COUNTRY, **kwargs):
    return generate_briefing(
        session,
        BriefingRequest(
            briefing_type=kind, **{"location_ids": {LOCATION}, "cutoff": CUTOFF, **kwargs}
        ),
    )


def observation(record_id=10, **overrides):
    return Evidence(
        **{
            "id": UUID(int=record_id),
            "analysis_run_id": RUN,
            "location_id": LOCATION,
            "source_id": SOURCE,
            "source_record_id": f"bulletin-{record_id}",
            "title": "Synthetic crossing bulletin",
            "summary": "The northern crossing reopened for freight.",
            "event_date": EVENT,
            "published_at": PUBLISHED,
            "retrieved_at": INGESTED,
            "created_at": INGESTED,
            "reliability": "reported",
            "url": "https://example.invalid/bulletin",
            "provenance": {"actors": ["North Valley Authority"], "conflict_id": "valley-1"},
            **overrides,
        }
    )


@pytest.fixture
def scope(session):
    session.add_all(
        [
            Location(id=LOCATION, name="North Valley", created_at=EVENT),
            Location(id=OTHER, name="South Valley", created_at=EVENT),
            Source(id=SOURCE, name="Synthetic Monitor", source_type="bulletin", created_at=EVENT),
        ]
    )
    session.flush()
    session.add(
        AnalysisRun(
            id=RUN,
            location_id=LOCATION,
            question="Synthetic security outlook",
            horizon_months=3,
            status="completed",
            pipeline_version="test",
            provider_config={},
            created_at=EVENT,
            completed_at=COMPLETED,
        )
    )
    session.flush()


@pytest.fixture
def complete(session, scope):
    work = KnowledgeWork(
        id=UUID(int=20),
        external_id="synthetic-work",
        title="Synthetic Logistics Handbook",
        author="Test Author",
        publication_year=2023,
        source_type="synthetic",
        source_provenance={"edition": "test"},
        created_at=EVENT,
        ingested_at=EVENT,
    )
    section = KnowledgeSection(
        id=UUID(int=21),
        work=work,
        section_identifier="1",
        title="Crossings",
        ordering=1,
        summary="",
        provenance={},
        created_at=EVENT,
    )
    session.add_all(
        [
            observation(),
            Indicator(
                id=UUID(int=11),
                location_id=LOCATION,
                name="Crossing delays",
                value=4,
                unit="hours",
                observed_at=EVENT,
                created_at=INGESTED,
                provenance={"source_name": "Synthetic Monitor", "source_record_id": "delays-1"},
            ),
            Forecast(
                id=UUID(int=12),
                analysis_run_id=RUN,
                conflict_type="interstate",
                question="Synthetic security outlook",
                horizon_months=3,
                version=1,
                probability_low=0.1,
                probability_high=0.2,
                confidence="low",
                rationale="MODEL RATIONALE MUST STAY OUT",
                evidence_for=["bulletin-10"],
                evidence_against=[],
                unknowns=[],
                resolution_criteria=[],
                change_conditions=[],
                created_at=COMPLETED,
            ),
            ForecastSignal(
                id=UUID(int=13),
                analysis_run_id=RUN,
                location_id=LOCATION,
                provider="Synthetic Signal",
                source_record_id="signal-1",
                model_name="Test Model",
                geographic_unit="country",
                source_location="North Valley",
                issue_date=PUBLISHED,
                target_start=datetime(2024, 7, 1, tzinfo=UTC),
                target_end=datetime(2024, 9, 30, tzinfo=UTC),
                target_variable="delays",
                prediction=3,
                unit="hours",
                retrieved_at=INGESTED,
                created_at=INGESTED,
                alignment_status="aligned",
                alignment_notes=[],
                provenance={},
            ),
            Scenario(
                id=UUID(int=14),
                analysis_run_id=RUN,
                name="Access interruption",
                description="Freight traffic could pause.",
                assumptions=["The crossing closes."],
                created_at=COMPLETED,
            ),
            StrategicClaim(
                id=UUID(int=22),
                external_id="synthetic-claim",
                work=work,
                section=section,
                attributed_author="Test Author",
                claim_text="Crossing capacity may shape logistics.",
                claim_type="theoretical",
                extraction_confidence="low",
                limitations=["Single setting"],
                counterexamples=["Alternate routes"],
                provenance={"page": 7},
                created_at=EVENT,
            ),
            StrategicAnalysis(
                id=UUID(int=23),
                analysis_run_id=RUN,
                lens_name="test",
                lens_version="1",
                retrieved_claim_ids=["synthetic-claim"],
                retrieved_case_ids=[],
                retrieval_provenance=[],
                output={"unverified": "MODEL RATIONALE MUST STAY OUT"},
                limitations=[],
                status="completed",
                created_at=COMPLETED,
                analyzed_at=COMPLETED,
            ),
        ]
    )
    session.commit()


def test_complete_and_source_attribution(session, complete):
    briefing = report(session)
    assert len(briefing.sections) == 9
    assert all(section.status == "available" for section in briefing.sections)
    data = json.loads(briefing.to_json())
    sources = {item["id"]: item for item in data["sources"]}
    for section in data["sections"]:
        for item in section["statements"]:
            assert item["citations"] and set(item["citations"]) <= sources.keys()
    evidence = next(
        source for source in briefing.sources if source.source_record_id == "bulletin-10"
    )
    assert (evidence.event_at, evidence.published_at, evidence.ingested_at) == (
        EVENT,
        PUBLISHED,
        INGESTED,
    )
    assert evidence.provenance["conflict_id"] == "valley-1"
    assert evidence.url == "https://example.invalid/bulletin"
    assert {item.kind for section in briefing.sections for item in section.statements} == {
        "observation",
        "forecast",
        "hypothetical",
        "interpretation",
    }
    markdown = briefing.to_markdown()
    assert "10.0% to 20.0% probability" in markdown
    assert "unverified" not in markdown
    assert "MODEL RATIONALE" not in briefing.to_json()


def test_empty_dataset(session):
    briefing = report(session)
    assert not briefing.sources
    assert all(
        section.status == "unavailable"
        for index, section in enumerate(briefing.sections)
        if index != 7
    )


def test_missing_dates_and_actors(session, scope):
    session.add(observation(event_date=None, published_at=None, provenance={}))
    session.flush()
    briefing = report(session)
    assert briefing.sections[1].status == briefing.sections[3].status == "unavailable"
    assert briefing.sections[2].statements[0].stale is None
    assert any("publication date" in gap for gap in briefing.sections[7].notes)


def test_conflict_preserves_both_sources(session, scope):
    alternative = Source(id=UUID(int=9), name="Synthetic Dispatch", source_type="bulletin")
    session.add(alternative)
    session.flush()
    session.add_all(
        [
            observation(
                provenance={"conflict_group": "north-crossing-26", "conflict_value": "open"}
            ),
            observation(
                15,
                source_id=alternative.id,
                summary="The northern crossing remained closed.",
                provenance={"conflict_group": "north-crossing-26", "conflict_value": "closed"},
            ),
        ]
    )
    session.flush()
    briefing = report(session)
    (disagreement,) = briefing.sections[7].statements
    assert set(disagreement.details["reported_values"].values()) == {"open", "closed"}
    assert len(disagreement.citations) == 2
    assert "remained closed" in briefing.to_markdown() and "reopened" in briefing.to_markdown()


def test_stale_observations_remain_attributed(session, scope):
    session.add(observation(event_date=EVENT - timedelta(days=120)))
    session.flush()
    briefing = report(session)
    assert briefing.sections[1].status == "unavailable"
    assert briefing.sections[2].statements[0].stale
    assert "**Observation (stale)**" in briefing.to_markdown()


@pytest.mark.parametrize("field", ["created_at", "retrieved_at", "published_at", "event_date"])
def test_cutoff_excludes_future_dates_independently(session, scope, field):
    future = datetime(2024, 7, 1, tzinfo=UTC)
    end_of_cutoff = future - timedelta(microseconds=1)
    session.add_all(
        [
            observation(10, **{field: future}),
            observation(11, **{field: end_of_cutoff}),
        ]
    )
    session.flush()
    briefing = report(session)
    assert {source.source_record_id for source in briefing.sources} == {"bulletin-11"}


def test_cutoff_excludes_late_run_products_but_allows_future_targets(session, complete):
    assert "2024-09-30" in report(session).to_json()
    historical = report(session, cutoff=EVENT.date())
    assert not historical.sources
    assert report(session, cutoff=INGESTED.date()).sections[5].status == "available"


def test_unresolved_and_ambiguous_forecast_citations_withhold_claim(session, complete):
    session.add(observation(15, source_record_id="bulletin-10"))
    session.flush()
    briefing = report(session)
    assert not any(source.id.startswith("forecasts/") for source in briefing.sources)
    assert any("withheld" in note for note in briefing.sections[7].notes)
    assert "20.0%" not in briefing.to_markdown()


def test_reproducible_across_query_order(session, complete):
    first = report(session)
    session.connection().exec_driver_sql("PRAGMA reverse_unordered_selects = ON")
    second = report(session)
    assert first.to_json() == second.to_json()
    assert first.to_markdown() == second.to_markdown()


def test_briefing_type_scope_and_weekly_window(session, complete):
    session.add_all(
        [
            observation(16, event_date=EVENT - timedelta(days=4)),
            observation(17, location_id=OTHER),
        ]
    )
    session.flush()
    regional = report(session, BriefingType.REGIONAL, location_ids={LOCATION, OTHER})
    assert {source.location_id for source in regional.sources} == {LOCATION, OTHER}
    weekly = report(session, BriefingType.WEEKLY)
    assert "bulletin-16" not in {source.source_record_id for source in weekly.sources}
    conflict = report(session, BriefingType.CONFLICT, conflict_id="valley-1")
    assert {source.source_record_id for source in conflict.sources} == {
        "bulletin-10",
        "bulletin-16",
    }
    assert any(
        item.kind == "interpretation"
        for item in report(session, BriefingType.OUTLOOK).sections[0].statements
    )
    with pytest.raises(ValidationError):
        report(session, BriefingType.CONFLICT)


def test_operational_event_uses_nested_timestamp_and_actor_fields(session, scope):
    session.add(
        Event(
            id=UUID(int=25),
            analysis_run_id=RUN,
            location_id=LOCATION,
            source_id=SOURCE,
            source_record_id="event-25",
            event_type="synthetic",
            occurred_at=EVENT,
            description="Synthetic event record.",
            confidence="reported",
            created_at=INGESTED,
            provenance={
                "actors": ["Test Actor"],
                "retrieved_at": INGESTED.isoformat(),
                "source_url": "https://example.invalid/event",
                "updated_at": datetime(2024, 7, 1, tzinfo=UTC).isoformat(),
                "provenance": {"conflict_id": "valley-1"},
            },
        )
    )
    session.flush()
    assert not report(session).sources
    briefing = report(
        session, BriefingType.CONFLICT, cutoff=date(2024, 7, 1), conflict_id="valley-1"
    )
    assert "Test Actor" in briefing.sections[3].statements[0].text
    assert briefing.sources[0].retrieved_at == INGESTED
