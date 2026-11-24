from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from test_historical_base_rates import observation

from geointel.connectors.ucdp import UCDPConnector
from geointel.domain.models import AnalysisRun, Event, Forecast
from geointel.domain.schemas import (
    AnalysisRequest,
    AnalystOutput,
    ConflictType,
    ForecastOutput,
    NormalizedConflictType,
    RedTeamOutput,
    SynthesisOutput,
)
from geointel.pipeline.historical import build_conflict_profile
from geointel.pipeline.service import AnalysisPipeline
from geointel.pipeline.taxonomy import MAPPING_VERSION, normalize_historical_type
from geointel.providers.base import ModelRouter
from geointel.providers.offline import OfflineModel

REFERENCE = date(2026, 1, 1)


@pytest.mark.parametrize(
    "value,meaning,target",
    [
        (1, "state-based conflict", "OTHER_OR_UNRESOLVED"),
        (2, "non-state conflict", "OTHER_OR_UNRESOLVED"),
        (3, "one-sided violence", "ONE_SIDED_VIOLENCE"),
        (99, None, "OTHER_OR_UNRESOLVED"),
        (None, None, "OTHER_OR_UNRESOLVED"),
        ("3", None, "OTHER_OR_UNRESOLVED"),
        (True, None, "OTHER_OR_UNRESOLVED"),
    ],
)
def test_verified_mapping_is_explicit_and_preserves_original(value, meaning, target):
    item = observation("mapping", 2020, type_of_violence=value)
    mapping = normalize_historical_type(item, "Spain")
    assert mapping.normalized_conflict_type.value == target
    assert mapping.provider_category_meaning == meaning
    assert mapping.provider_original_categories["type_of_violence"] == value
    assert mapping.mapping_method_version == MAPPING_VERSION
    assert mapping.mapping_notes
    assert mapping.provider == "UCDP"
    assert mapping.provider_dataset == "GED"
    assert mapping.dataset_version == "26.1"
    assert mapping.requested_geography == "Spain"
    assert mapping.resolved_provider_geography_id == 230
    assert mapping.source_record_id == "mapping"
    assert mapping.temporal_role == "annual_historical"


def test_no_mapping_by_code_alone_or_target_label():
    item = observation(1, 2020, type_of_violence=3, conflict_type="INTERNAL_ARMED_CONFLICT")
    item.source_name = "Unknown"
    assert (
        normalize_historical_type(item, "Spain").normalized_conflict_type.value
        == "OTHER_OR_UNRESOLVED"
    )
    item.source_name = "UCDP"
    item.provenance["dataset"] = "GED Candidate"
    item.provenance["temporal_role"] = "candidate_recent"
    assert build_conflict_profile([item], "Spain", REFERENCE).status == "unavailable"


def test_grouping_fatalities_temporal_windows_and_reversal():
    items = [
        observation(1, 2010, 2, 1, 3, type_of_violence=1),
        observation(2, 2020, 4, 3, 5, type_of_violence=3),
        observation(3, 2020, 6, type_of_violence=3),
        observation(4, 2025, 0, 0, 0, type_of_violence=2),
    ]
    profile = build_conflict_profile(items, "Spain", REFERENCE)
    assert profile == build_conflict_profile(list(reversed(items)), "Spain", REFERENCE)
    assert set(profile.conflict_types) == set(NormalizedConflictType)
    assert profile.overall.observation_statistics.observation_count == 4
    assert (
        sum(x.observation_statistics.observation_count for x in profile.conflict_types.values())
        == 4
    )
    assert profile.unresolved_observation_count == 2
    one = profile.conflict_types[NormalizedConflictType.ONE_SIDED_VIOLENCE]
    assert one.observation_statistics.dated_observation_count == 2
    assert one.observation_statistics.distinct_observed_year_count == 1
    assert one.observation_statistics.observed_year_span == 1
    assert one.observation_statistics.years_since_latest_observation == 6
    assert one.observation_statistics.earliest_observation_date == date(2020, 1, 1)
    assert one.observation_statistics.latest_observation_date == date(2020, 1, 1)
    assert one.fatality_statistics.best_total == 10
    assert one.fatality_statistics.low_total == 3
    assert one.fatality_statistics.high_total == 5
    assert one.fatality_statistics.best_available_count == 2
    assert one.fatality_statistics.low_available_count == 1
    assert one.fatality_statistics.median_best_per_observation == 5
    assert one.fatality_statistics.maximum_best_per_observation == 6
    assert one.share_of_retrieved_historical_observations == 0.5
    assert one.trailing_window_counts == {"0": {"5y": 0, "10y": 2, "20y": 2}}
    assert profile.overall.fatality_statistics.best_total == 12
    assert profile.overall.observation_statistics.distinct_observed_year_count == 3
    assert profile.overall.observation_statistics.observed_year_span == 16
    assert not profile.conflict_types[
        NormalizedConflictType.INTERSTATE_ARMED_CONFLICT
    ].historical_presence
    assert (
        profile.conflict_types[
            NormalizedConflictType.INTERSTATE_ARMED_CONFLICT
        ].fatality_statistics.best_total
        is None
    )
    fields = type(profile.overall.observation_statistics).model_fields
    assert "episode_count" not in fields and "conflict_count" not in fields
    assert any("episodes" in c for c in profile.caveats)


@pytest.mark.parametrize(
    "start,end,status",
    [
        (None, None, "UNAVAILABLE_UNKNOWN_COVERAGE"),
        ("1989-01-01", None, "UNAVAILABLE_UNKNOWN_COVERAGE"),
        (None, "2025-12-31", "UNAVAILABLE_UNKNOWN_COVERAGE"),
        ("1989-01-01", "2025-12-31", "UNAVAILABLE_UNVALIDATED_DENOMINATOR"),
    ],
)
def test_denominators_never_inferred(start, end, status):
    item = observation(1, 2020, type_of_violence=3, coverage_start=start, coverage_end=end)
    profile = build_conflict_profile([item], "Spain", REFERENCE)
    assert profile.coverage[0].coverage_start == (date.fromisoformat(start) if start else None)
    assert profile.coverage[0].coverage_end == (date.fromisoformat(end) if end else None)
    assert profile.annualized_rate_status == status
    assert profile.annualized_observation_rate is None
    assert profile.overall.observation_statistics.distinct_observed_year_count == 1
    assert any("zero-conflict" in c for c in profile.caveats)


def test_empty_missing_dates_fatalities_and_multi_dataset_references():
    empty = build_conflict_profile([], "Spain", REFERENCE)
    assert empty.status == "unavailable"
    assert empty.overall.share_of_retrieved_historical_observations is None
    assert empty.overall.trailing_window_counts == {}
    missing = observation(1, 2020, coverage_end=None)
    missing.event_date = None
    missing.provenance["fatalities"] = None
    profile = build_conflict_profile([missing], "Spain", REFERENCE)
    assert profile.overall.observation_statistics.dated_observation_count == 0
    assert profile.overall.observation_statistics.years_since_latest_observation is None
    assert profile.coverage[0].reference_date is None
    assert profile.overall.fatality_statistics.best_total is None
    assert profile.unresolved_observation_count == 1
    a = observation(2, 2020, type_of_violence=3, reference_date="2020-02-29")
    b = observation(3, 2015, type_of_violence=3, dataset_version="25.1", coverage_end=None)
    profile = build_conflict_profile([a, b], "Spain", REFERENCE)
    assert len(profile.coverage) == 2
    assert len(profile.overall.trailing_window_counts) == 2
    assert all(m.coverage_index in {"0", "1"} for m in profile.normalization_audit)


def test_exact_trailing_window_boundaries_and_leap_reference():
    items = [
        observation(1, 2015, type_of_violence=3, reference_date="2020-02-29"),
        observation(2, 2015, type_of_violence=3, reference_date="2020-02-29"),
        observation(3, 2020, type_of_violence=3, reference_date="2020-02-29"),
    ]
    items[0].event_date = datetime(2015, 2, 28, tzinfo=UTC)
    items[1].event_date = datetime(2015, 3, 1, tzinfo=UTC)
    items[2].event_date = datetime(2020, 3, 1, tzinfo=UTC)
    profile = build_conflict_profile(items, "Spain", REFERENCE)
    assert profile.overall.trailing_window_counts["0"]["5y"] == 1


def test_connector_preserves_explicit_boundaries_and_original_code():
    item = UCDPConnector("https://example.invalid", "26.1").normalize(
        {
            "id": 1,
            "country": "Spain",
            "country_id": 230,
            "type_of_violence": 3,
            "coverage_start": "1989-01-01",
            "date_start": "2020-01-01",
        },
        "Spain",
    )
    profile = build_conflict_profile([item], "Spain", REFERENCE)
    assert profile.coverage[0].coverage_start == date(1989, 1, 1)
    assert profile.coverage[0].coverage_end is None
    assert profile.normalization_audit[0].provider_original_value == 3
    assert profile.normalization_audit[0].resolved_provider_geography_id == 230


def profile_payload():
    items = [observation(i, 2020, 2, type_of_violence=3 if i % 2 else 1) for i in range(48)]
    from geointel.pipeline.historical import summarize_history

    return {
        "historical_conflict_profile": build_conflict_profile(items, "Spain", REFERENCE).model_dump(
            mode="json"
        ),
        "historical_base_rate_summary": summarize_history(items, "Spain", REFERENCE).model_dump(
            mode="json"
        ),
        "historical_evidence": [x.model_dump(mode="json") for x in items],
        "observed_evidence": [],
        "collection_metadata": {"current_operational_coverage_available": False},
    }


def test_compact_analyst_forecast_and_synthesis_context():
    model, payload = OfflineModel(), profile_payload()
    analyst = model.generate("analyst", payload, AnalystOutput)
    assert analyst.observed_evidence == []
    assert len(analyst.historical_evidence) == 1
    assert "ONE_SIDED_VIOLENCE" in analyst.historical_evidence[0]
    assert "24 unresolved" in analyst.historical_evidence[0]
    assert not any("Historical observation 1" in x for x in analyst.historical_evidence)
    forecast = model.generate("forecaster", payload, ForecastOutput)
    red = model.generate(
        "red_team",
        {
            **payload,
            "analysis": analyst.model_dump(mode="json"),
            "forecast": forecast.model_dump(mode="json"),
        },
        RedTeamOutput,
    )
    assert not red.historical_semantic_concerns
    assert not red.taxonomy_normalization_concerns
    synthesis = model.generate(
        "synthesis",
        {**payload, "red_team": red.model_dump(), "forecast": forecast.model_dump()},
        SynthesisOutput,
    )
    synthesis.validate_red_team_incorporation(red)
    for assessment in synthesis.assessments:
        assert assessment.probability_low is assessment.probability_high is None
        assert assessment.confidence.value == "low"
        assert any("Historical observations mapped" in note for note in assessment.unknowns)
    one = next(x for x in synthesis.assessments if x.conflict_type == ConflictType.ONE_SIDED)
    assert any("24 retrieved observations" in note for note in one.unknowns)


@pytest.mark.parametrize(
    "claim,field",
    [
        ("48 historical conflicts occurred.", "historical_semantic_concerns"),
        ("48 episodes occurred.", "historical_semantic_concerns"),
        ("Fatality totals are event frequency.", "historical_semantic_concerns"),
        ("Historical frequency implies probability.", "historical_semantic_concerns"),
        ("Historical presence means current activity.", "historical_semantic_concerns"),
        ("Historical presence increases escalation.", "historical_semantic_concerns"),
        ("Latest observation is dataset coverage end.", "base_rate_concerns"),
        ("Missing years are zero-conflict years.", "base_rate_concerns"),
        ("Provider code 1 means internal conflict.", "taxonomy_normalization_concerns"),
    ],
)
def test_red_team_detects_claim_misuse(claim, field):
    red = OfflineModel().generate(
        "red_team",
        {**profile_payload(), "analysis": {"historical_base_rate_notes": [claim]}},
        RedTeamOutput,
    )
    assert getattr(red, field)


def test_red_team_detects_structured_mapping_loss_and_escalation():
    payload = profile_payload()
    profile = payload["historical_conflict_profile"]
    profile["normalization_audit"].pop()
    profile["unresolved_observation_count"] = 0
    profile["annualized_observation_rate"] = 0.5
    payload["escalation_indicators"] = ["history"]
    payload["forecast"] = {"assessments": [{"probability_low": 0.5}]}
    red = OfflineModel().generate("red_team", payload, RedTeamOutput)
    assert len(red.taxonomy_normalization_concerns) == 2
    assert red.historical_semantic_concerns
    assert any("denominator" in x for x in red.base_rate_concerns)
    assert any("Historical features" in x for x in red.unjustified_precision)


def test_profile_persistence_history_alone_has_no_current_outputs(session):
    class History:
        def collect(self, location, horizon_months):
            return [observation(1, 2020, 2, type_of_violence=3)]

    model = OfflineModel()
    run = AnalysisPipeline(session, ModelRouter(model, model, model), [History()]).run(
        AnalysisRequest(
            location="Spain",
            question="Assess organized violence over twelve months.",
            horizon_months=12,
        )
    )
    session.expire_all()
    saved = session.get(AnalysisRun, run.id)
    profile = saved.collection_metadata["historical_conflict_profile"]
    assert profile == saved.analyst_output["historical_conflict_profile"]
    assert profile["normalization_audit"][0]["provider_original_value"] == 3
    assert saved.analyst_output["observed_evidence"] == []
    assert not saved.collection_metadata["current_operational_coverage_available"]
    assert saved.collection_metadata["current_evidence_count"] == 0
    assert not list(session.scalars(select(Event)))
    assert all(
        f.probability_low is f.probability_high is None for f in session.scalars(select(Forecast))
    )


def test_historical_profile_changes_do_not_create_monitoring_escalation(session):
    from geointel.domain.models import Alert
    from geointel.monitoring import MonitoringService

    class History:
        count = 1

        def collect(self, location, horizon_months):
            return [observation(i, 2020, type_of_violence=3) for i in range(self.count)]

    history, model = History(), OfflineModel()
    svc = MonitoringService(
        session, lambda: AnalysisPipeline(session, ModelRouter(model, model, model), [history])
    )
    target = svc.add_target(svc.create_watchlist("Synthetic historical only"), "SYN", "Spain")
    svc.run_target(target)
    history.count = 48
    svc.run_target(target)
    assert session.scalars(select(Alert)).all() == []


def test_synthesis_removes_uncalibrated_history_probabilities():
    payload, model = profile_payload(), OfflineModel()
    forecast = model.generate("forecaster", payload, ForecastOutput).model_dump(mode="json")
    forecast["assessments"][0].update(probability_low=0.1, probability_high=0.5)
    red = model.generate("red_team", {**payload, "forecast": forecast}, RedTeamOutput)
    result = model.generate(
        "synthesis",
        {**payload, "forecast": forecast, "red_team": red.model_dump()},
        SynthesisOutput,
    )
    result.validate_red_team_incorporation(red)
    assert all(x.probability_low is x.probability_high is None for x in result.assessments)


def test_red_team_catches_forged_normalized_code():
    payload = profile_payload()
    mapping = payload["historical_conflict_profile"]["normalization_audit"][0]
    mapping["normalized_conflict_type"] = "INTERNAL_ARMED_CONFLICT"
    red = OfflineModel().generate("red_team", payload, RedTeamOutput)
    assert any("deterministic mapping" in x for x in red.taxonomy_normalization_concerns)


def test_profile_schema_rejects_numeric_annualized_rate():
    from pydantic import ValidationError

    from geointel.domain.schemas import HistoricalConflictProfile

    profile = profile_payload()["historical_conflict_profile"]
    profile["annualized_observation_rate"] = 0.5
    with pytest.raises(ValidationError):
        HistoricalConflictProfile.model_validate(profile)


def test_pipeline_refuses_numeric_synthesis_from_other_routed_model(session):
    class UncalibratedModel(OfflineModel):
        def generate(self, role, payload, output_type):
            result = super().generate(role, payload, output_type)
            if output_type is SynthesisOutput:
                result.assessments[0].probability_low = 0.1
                result.assessments[0].probability_high = 0.5
            return result

    model = UncalibratedModel()
    with pytest.raises(ValueError, match="no calibrated probability mechanism"):
        AnalysisPipeline(session, ModelRouter(model, model, model)).run(
            AnalysisRequest(
                location="Spain",
                question="Assess organized violence over twelve months.",
                horizon_months=12,
            )
        )
    assert session.scalars(select(Forecast)).all() == []


def test_invalid_missing_fatality_values_are_not_zero_imputed():
    item = observation(1, 2020, -1, True, "4", type_of_violence=3)
    profile = build_conflict_profile([item], "Spain", REFERENCE)
    stats = profile.overall.fatality_statistics
    assert stats.best_total is stats.low_total is stats.high_total is None
    assert (
        stats.best_available_count == stats.low_available_count == stats.high_available_count == 0
    )


def test_profile_is_sufficient_for_normalized_analyst_context_without_raw_rows():
    payload = {"historical_conflict_profile": profile_payload()["historical_conflict_profile"]}
    analyst = OfflineModel().generate("analyst", payload, AnalystOutput)
    assert analyst.historical_evidence and "ONE_SIDED_VIOLENCE" in analyst.historical_evidence[0]
    assert analyst.observed_evidence == []
    assert analyst.historical_base_rate_summary is None
    red = OfflineModel().generate("red_team", payload, RedTeamOutput)
    assert not any("No validated historical" in x for x in red.missing_evidence)


@pytest.mark.parametrize("mixed", [False, True])
def test_routed_model_history_changes_leave_alerts_untouched(session, mixed, monkeypatch):
    from test_collection_coverage import NOW, Clock

    from geointel.domain.models import Alert
    from geointel.domain.schemas import (
        Confidence,
        NormalizedForecastSignal,
        NormalizedOperationalEvent,
    )
    from geointel.monitoring import MonitoringService

    monkeypatch.setattr("geointel.pipeline.service.datetime", Clock)

    class Inputs:
        count = 0
        taxonomy = 3
        events = ()
        signals = ()

        def collect(self, location, horizon_months):
            return [
                *(observation(i, 2026, type_of_violence=self.taxonomy) for i in range(self.count)),
                *(
                    NormalizedOperationalEvent(
                        provider=provider,
                        source_record_id=identity,
                        event_date=NOW,
                        event_type="Battles",
                        country="Spain",
                        retrieved_at=NOW,
                    )
                    for provider, identity in self.events
                ),
                *(
                    NormalizedForecastSignal(
                        provider=provider,
                        source_record_id="signal",
                        model_name="Synthetic forecast",
                        geographic_unit="country",
                        location="Spain",
                        issue_date=NOW,
                        target_start=NOW,
                        target_end=NOW + timedelta(days=30),
                        prediction=2,
                        target_variable="events",
                        retrieved_at=NOW,
                    )
                    for provider in self.signals
                ),
            ]

    class RoutedModel(OfflineModel):
        variant = 0

        def generate(self, role, payload, output_type):
            result = super().generate(role, payload, output_type)
            if output_type is SynthesisOutput:
                assessment = result.assessments[0]
                history = payload["historical_evidence"]
                variant = len(history) or self.variant
                if history and history[0]["provenance"]["type_of_violence"] == 1:
                    variant += 1
                assessment.confidence = Confidence.HIGH if variant == 2 else Confidence.LOW
                assessment.evidence_for = [f"Model evidence {variant}"]
                assessment.unknowns = [f"Model unknown {variant}"]
            return result

    inputs, model = Inputs(), RoutedModel()
    if mixed:
        inputs.events = (("ACLED", "stable"),)
    svc = MonitoringService(
        session, lambda: AnalysisPipeline(session, ModelRouter(model, model, model), [inputs])
    )
    target = svc.add_target(svc.create_watchlist("Routed historical isolation"), "ESP", "Spain")
    first = svc.run_target(target)
    assert first.baseline_established

    inputs.count = 1
    one = svc.run_target(target)
    inputs.count = 2
    two = svc.run_target(target)
    assert one.status == two.status == "completed"
    assert session.scalars(select(Alert)).all() == []
    if mixed:
        records = svc._snapshot(two.analysis_run)["assessment_records"]
        assert len(records["event_ids"]) == 1
    for kind in ("forecast_change", "uncertainty_change"):
        assert any(c.change_type == kind and not c.material for c in two.changes)

    # Seed a real history-free alert with the same routed after-state.
    inputs.count = 0
    model.variant = 1
    svc.run_target(target)
    model.variant = 2
    svc.run_target(target)
    alert = session.scalars(select(Alert)).one()
    observed = alert.last_observed_at
    inputs.count = 1
    svc.run_target(target)
    inputs.count = 2
    repeated = svc.run_target(target)
    assert repeated.status == "completed"
    assert session.scalars(select(Alert)).one().last_observed_at == observed

    inputs.taxonomy = 1
    remapped = svc.run_target(target)
    assert remapped.status == "completed"
    assert (
        remapped.analysis_run.collection_metadata["historical_conflict_profile"]
        != (repeated.analysis_run.collection_metadata["historical_conflict_profile"])
    )
    assert session.scalars(select(Alert)).one().last_observed_at == observed

    assert any(c.change_type == "forecast_change" and not c.material for c in remapped.changes)

    inputs.events += (("ACLED", "new"), ("Independent fixture", "new"))
    events = svc.run_target(target)
    assert any(c.change_type == "new_operational_events" and c.material for c in events.changes)
    assert len(session.scalars(select(Alert)).all()) == 2

    inputs.signals = ("CAST", "VIEWS")
    signals = svc.run_target(target)
    assert {c.change_type for c in signals.changes if c.material} == {"predictive_signal_change"}
    assert len(session.scalars(select(Alert)).all()) == 3
