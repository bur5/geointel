from datetime import UTC, date, datetime

from sqlalchemy import select

from geointel.connectors.ucdp import UCDPConnector
from geointel.domain.models import Evidence
from geointel.domain.schemas import (
    AnalysisRequest,
    AnalystOutput,
    NormalizedEvidence,
    RedTeamOutput,
)
from geointel.pipeline.historical import summarize_history
from geointel.pipeline.service import AnalysisPipeline
from geointel.providers.base import ModelRouter
from geointel.providers.offline import OfflineModel


def observation(index, year, best=None, low=None, high=None, **extra):
    return NormalizedEvidence(
        source_name="UCDP",
        source_record_id=str(index),
        title="Historical record",
        summary=f"Historical observation {index}",
        event_date=datetime(year, 1, 1, tzinfo=UTC),
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        geographic_scope="Spain",
        provenance={
            "temporal_role": "annual_historical",
            "dataset": "GED",
            "dataset_version": "26.1",
            "resolved_ucdp_country_id": 230,
            "coverage_end": "2025-12-31",
            "fatalities": {"best": best, "low": low, "high": high},
            **extra,
        },
    )


def test_deterministic_statistics_and_censoring():
    items = [
        observation(1, 2010, 2, 1, 3, type_of_violence=1),
        observation(2, 2020, 4, 3, 5),
        observation(3, 2020, 6),
    ]
    summary = summarize_history(items, "Spain", date(2026, 1, 1))
    assert summary == summarize_history(list(reversed(items)), "Spain", date(2026, 1, 1))
    stats = summary.observation_statistics
    assert (stats.observation_count, stats.distinct_observed_year_count) == (3, 2)
    assert stats.observed_year_span == 11
    assert stats.years_since_latest_observation == 6
    fatalities = summary.fatality_statistics
    assert (fatalities.best_total, fatalities.low_total, fatalities.high_total) == (12, 4, 8)
    assert fatalities.low_available_count == 2
    assert fatalities.median_best_per_observation == 4
    assert fatalities.maximum_best_per_observation == 6
    assert summary.coverage[0].coverage_end == date(2025, 12, 31)
    assert summary.trailing_window_counts == {"0": {"5y": 0, "10y": 2, "20y": 3}}
    assert summary.category_statistics == {"type_of_violence": {"1": 1}}


def test_empty_and_missing_optional_fields():
    empty = summarize_history([], "Spain", date(2026, 1, 1))
    assert empty.status == "unavailable"
    assert empty.fatality_statistics.best_total is None
    item = observation(1, 2020)
    item.event_date = None
    item.provenance.pop("coverage_end")
    summary = summarize_history([item], "Spain", date(2026, 1, 1))
    assert summary.category_statistics == {}
    assert summary.coverage[0].coverage_end is None
    assert summary.observation_statistics.latest_year is None
    assert summary.trailing_window_counts == {}


def test_history_only_pipeline_persistence_and_no_probability(session):
    class Fixture:
        connector_name = "UCDP"

        def collect(self, location, horizon_months):
            return [observation(1, 2020, 2, 1, 3)]

    model = OfflineModel()
    run = AnalysisPipeline(session, ModelRouter(model, model, model), [Fixture()]).run(
        AnalysisRequest(
            location="Spain",
            question="Assess organized violence over twelve months.",
            horizon_months=12,
        )
    )
    assert run.analyst_output["observed_evidence"] == []
    assert run.analyst_output["historical_evidence"]
    assert run.analyst_output["historical_base_rate_summary"]["status"] == "available"
    assert not run.collection_metadata["current_operational_coverage_available"]
    assert run.collection_metadata["recent_event_count"] == 0
    assert run.collection_metadata["historical_conflict_coverage_available"]
    assert session.scalar(select(Evidence)).provenance["temporal_role"] == "annual_historical"
    assert "context available" in run.synthesis_output["summary"]
    assert "No validated current operational" in run.synthesis_output["summary"]
    for assessment in run.synthesis_output["assessments"]:
        assert assessment["probability_low"] is assessment["probability_high"] is None
        assert not any("base rates are unavailable" in s for s in assessment["unknowns"])


def test_explicit_role_over_provider_name_and_red_team_leakage():
    item = observation(1, 2020, 2)
    item.source_name = "Other historical provider"
    summary = summarize_history([item], "Spain", date(2026, 1, 1)).model_dump(mode="json")
    payload = {
        "observed_evidence": [item.model_dump(mode="json")],
        "historical_evidence": [item.model_dump(mode="json")],
        "historical_base_rate_summary": summary,
    }
    red = OfflineModel().generate("red_team", payload, RedTeamOutput)
    assert "Temporal leakage" in red.temporal_leakage_concerns[0]
    item.provenance["temporal_role"] = "candidate_recent"
    assert summarize_history([item], "Spain", date(2026, 1, 1)).status == "unavailable"


def test_real_normalizer_history_cannot_enter_observed():
    item = UCDPConnector(base_url="https://example.invalid", api_version="26.1").normalize(
        {"id": 1, "country": "Spain", "country_id": 230, "date_start": "2020-01-01", "best": 2},
        "Spain",
    )
    payload = {"historical_evidence": [item.model_dump(mode="json")], "observed_evidence": []}
    assert OfflineModel().generate("analyst", payload, AnalystOutput).observed_evidence == []


def test_provider_explicit_coverage_end_survives_normalization():
    item = UCDPConnector(base_url="https://example.invalid", api_version="26.1").normalize(
        {
            "id": 1,
            "country": "Spain",
            "country_id": 230,
            "date_start": "2020-01-01",
            "coverage_end": "2025-12-31",
            "reference_date": "2025-12-31",
        },
        "Spain",
    )
    summary = summarize_history([item], "Spain", date(2026, 1, 1))
    assert summary.coverage[0].coverage_end == date(2025, 12, 31)
    assert summary.coverage[0].reference_basis == "provider_reference"


def test_current_and_unclassified_records_remain_separate(session):
    class Mixed:
        def collect(self, location, horizon_months):
            history = observation(1, 2020, 2)
            current = observation(2, 2026, 1)
            current.provenance["temporal_role"] = "current_operational"
            unknown = observation(3, 2024, 3)
            unknown.provenance.pop("temporal_role")
            return [history, current, unknown]

    model = OfflineModel()
    run = AnalysisPipeline(session, ModelRouter(model, model, model), [Mixed()]).run(
        AnalysisRequest(
            location="Spain",
            question="Assess organized violence over twelve months.",
            horizon_months=12,
        )
    )
    assert run.analyst_output["observed_evidence"] == ["Historical observation 2"]
    assert run.collection_metadata["historical_observation_count"] == 1
    assert run.collection_metadata["unclassified_evidence_count"] == 1
    assert session.query(Evidence).count() == 3
