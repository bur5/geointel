from typing import TypeVar

from pydantic import BaseModel

from geointel.domain.schemas import (
    AnalystOutput,
    Confidence,
    ConflictType,
    ForecastOutput,
    HistoricalBaseRateSummary,
    HistoricalConflictProfile,
    RedTeamOutput,
    RiskAssessment,
    SynthesisOutput,
)
from geointel.pipeline.historical_review import historical_context, review_historical_claims

T = TypeVar("T", bound=BaseModel)


class OfflineModel:
    """Deterministic, explicitly non-live model for reproducible development—not intelligence."""

    name = "offline-rules-v1"

    def generate(self, role: str, payload: dict, output_type: type[T]) -> T:
        evidence = payload.get("observed_evidence", payload.get("evidence", []))
        historical = payload.get("historical_evidence", [])
        summary = payload.get("historical_base_rate_summary")
        history_available = bool(summary and summary["status"] == "available")
        history_note = (
            f"Historical base-rate context available: "
            f"{summary['observation_statistics']['observation_count']} observations; "
            "historical features are not forecast probabilities."
            if history_available
            else "No validated historical base-rate observations are available."
        )
        profile = payload.get("historical_conflict_profile")
        if profile:
            history_available = profile["status"] == "available"
            history_note = (
                historical_context(profile)
                if history_available
                else "No validated historical base-rate observations are available."
            )
        signals = payload.get("predictive_signals", [])
        recent_events = payload.get("recent_events", [])
        news_reports = payload.get("news_reports", [])
        metadata = payload.get("collection_metadata", {})
        delayed_news = bool(metadata.get("delayed_news_discovery_coverage_available"))
        operational = bool(
            payload.get(
                "assessment_operational_records_available",
                metadata.get("current_operational_coverage_available"),
            )
        )
        if output_type is AnalystOutput:
            result = AnalystOutput(
                observed_evidence=[
                    e["summary"]
                    for e in evidence
                    if e.get("provenance", {}).get("temporal_role")
                    not in {"annual_historical", "historical"}
                ],
                historical_evidence=[history_note] if historical or history_available else [],
                historical_conflict_profile=(
                    HistoricalConflictProfile.model_validate(profile) if profile else None
                ),
                historical_base_rate_summary=(
                    HistoricalBaseRateSummary.model_validate(summary) if summary else None
                ),
                recent_events=[
                    f"ACLED reported {item['event_type']} on {item['event_date']} "
                    f"({item['alignment_status']}); report is not independently verified."
                    for item in recent_events
                ],
                predictive_signals=[
                    (
                        f"{item['provider']} model output {item['source_record_id']} for "
                        f"{item['target_variable']} ({item['alignment_status']}); "
                        "prediction retained in the source record without reinterpretation."
                    )
                    for item in signals
                ],
                source_disagreements=payload.get("source_disagreements", []),
                missing_sources=[
                    item["connector"]
                    for item in metadata.get("connector_outcomes", [])
                    if not item["succeeded"]
                ],
                historical_base_rate_notes=[history_note],
                assumptions=[
                    "Absence of retrieved evidence is not evidence of absence.",
                    (
                        "Delayed news-discovery reports are available as unconfirmed leads, but "
                        "no validated current operational event coverage is available."
                        if delayed_news and not operational
                        else "No validated current operational event coverage is available."
                        if not operational
                        else "Validated operational records and unconfirmed news leads retain "
                        "separate evidentiary status."
                    ),
                    "Media reports are unconfirmed and may be syndicated, incomplete, biased, "
                    "duplicated, or contradictory; article volume is not event frequency.",
                ],
                strategic_context=[
                    f"{item['lens_name']} output is an interpretation, not evidence."
                    for item in payload.get("strategic_context", [])
                ],
            )
        elif output_type is ForecastOutput:
            assessments = []
            for kind in ConflictType:
                assessments.append(
                    RiskAssessment(
                        conflict_type=kind,
                        probability_low=None,
                        probability_high=None,
                        confidence=Confidence.LOW,
                        rationale=(
                            "Insufficient validated operational evidence to quantify risk; "
                            "delayed news-discovery reports may be available as unconfirmed leads."
                        ),
                        evidence_for=[],
                        evidence_against=[],
                        unknowns=[
                            (
                                "No validated current operational event coverage is available. "
                                "Delayed news-discovery reports are "
                                "not confirmed Events or Evidence."
                                if delayed_news and not operational
                                else "No validated current operational event coverage is available."
                                if not operational
                                else "Operational reports require independent review."
                            ),
                            historical_context(profile, kind) if profile else history_note,
                            "No calibrated forecast probability model is available.",
                        ],
                        resolution_criteria=[
                            f"Observe whether qualifying {kind.value} occurs within the horizon."
                        ],
                        change_conditions=[
                            "Multiple independent, reliable sources document escalation indicators."
                        ],
                    )
                )
            result = ForecastOutput(
                assessments=assessments,
                overall_summary=(
                    "Evidence is insufficient for a quantified assessment; "
                    "no alarming conclusion is inferred."
                ),
            )
        elif output_type is RedTeamOutput:
            mismatch_notes = payload.get("source_disagreements", [])
            result = RedTeamOutput(
                missing_evidence=(
                    ["No validated current operational event coverage is available."]
                    if not operational
                    else []
                )
                + ([] if history_available else [history_note]),
                temporal_leakage_concerns=[
                    "Temporal leakage: historical evidence presented as current."
                    for item in evidence
                    if item.get("provenance", {}).get("temporal_role")
                    in {"annual_historical", "historical"}
                ]
                + (
                    ["Temporal leakage: historical narrative presented as current."]
                    if set(payload.get("analysis", {}).get("observed_evidence", []))
                    & {item["summary"] for item in historical}
                    else []
                )
                + (
                    ["Temporal leakage: historical coverage asserted as current coverage."]
                    if history_available and operational and not recent_events and not evidence
                    else []
                ),
                base_rate_concerns=[
                    "Dataset coverage end must not be mistaken for present-day coverage.",
                    "Historical frequency is not forecast probability; fatalities are not events.",
                    "Sparse historical observations cannot establish a trend.",
                    "Missing categories must not be inferred.",
                ]
                if history_available
                else [],
                unjustified_precision=[
                    "Do not assign numeric probabilities without calibrated data."
                ]
                + (
                    ["Historical features do not justify uncalibrated forecast probabilities."]
                    if history_available
                    and any(
                        item.get("probability_low") is not None
                        for item in payload.get("forecast", {}).get("assessments", [])
                    )
                    else []
                ),
                false_positive_risks=[
                    "Political tension must not be conflated with organized violence."
                ],
                predictive_signal_concerns=(
                    [
                        "VIEWS/CAST output is predictive, not observed factual evidence; "
                        "do not convert its value into a GEOINTEL probability."
                    ]
                    if signals
                    else ["No VIEWS or CAST predictive signal was available."]
                ),
                duplicated_evidence=[
                    "Reports may be semantically clustered as a probable story, while source "
                    "dependence may remain unresolved; multiple domains are not independent "
                    "corroboration and shared wire/upstream reporting must not be double-counted."
                ]
                if recent_events or news_reports
                else [],
                sensationalism_risks=[
                    "News reports are discovery leads, not confirmed events or independent "
                    "corroboration; publication volume is not conflict probability."
                ]
                if news_reports
                else [],
                geographic_mismatches=[x for x in mismatch_notes if "geographic" in x],
                horizon_mismatches=[x for x in mismatch_notes if "horizon" in x],
                stale_event_concerns=[x for x in mismatch_notes if "stale event" in x],
                sparse_coverage_concerns=[
                    "Sparse operational coverage cannot establish absence or a trend."
                ]
                if len(recent_events) < 2
                else [],
                fatality_uncertainty=[
                    "Reported ACLED fatalities must not be treated as perfectly precise."
                ]
                if recent_events
                else [],
                causal_claim_concerns=[
                    "Event classifications alone do not establish motive or causation."
                ]
                if recent_events
                else [],
                authority_bias=[
                    "A famous author or named lens has no authority to override empirical evidence."
                ]
                if payload.get("strategic_context")
                else [],
                analogy_misuse=[
                    "Historical analogy alone cannot justify escalation; applicability and "
                    "mismatch must be explicit."
                ]
                if payload.get("strategic_context")
                else [],
                theory_override_concerns=[
                    "Strategic theory is attributed interpretation, not a fact, causal law, or "
                    "probability."
                ]
                if payload.get("strategic_context")
                else [],
                selective_retrieval_concerns=[
                    "Deterministic retrieval may omit relevant claims; review exclusions and "
                    "provenance."
                ]
                if payload.get("strategic_context")
                else [],
                missing_alternative_theories=[
                    "The Kissinger lens may be uninformative; compare an alternative theoretical "
                    "lens."
                ]
                if payload.get("strategic_context")
                else [],
                retrospective_determinism=[
                    "Do not read a known historical outcome as inevitable or transferable."
                ]
                if payload.get("strategic_context")
                else [],
                confirmation_bias=[
                    "Seek claims and present evidence that could disconfirm the preferred frame."
                ]
                if payload.get("strategic_context")
                else [],
                outdated_geopolitical_assumptions=[
                    "Historical assumptions about actors and order require current validation."
                ]
                if payload.get("strategic_context")
                else [],
            )
            for field, findings in review_historical_claims(payload).items():
                setattr(result, field, sorted(set(getattr(result, field) + findings)))
        elif output_type is SynthesisOutput:
            critique = payload["red_team"]
            result = SynthesisOutput(
                summary=(
                    "Insufficient evidence for quantified risk. The red-team review requires "
                    "restraint and additional independent data. "
                    + history_note
                    + " "
                    + (
                        "No validated current operational event coverage is available."
                        if not operational
                        else "Operational records remain separately identified."
                    )
                ),
                assessments=[
                    RiskAssessment.model_validate(
                        {**x, "probability_low": None, "probability_high": None}
                    )
                    for x in payload["forecast"]["assessments"]
                ],
                incorporated_critiques=[
                    finding
                    for findings in critique.values()
                    for finding in findings
                    if finding.strip()
                ],
                decision_support_notice=(
                    "This output supports human judgment; it is not a verified intelligence "
                    "product or decision."
                ),
            )
        else:
            raise TypeError(f"Unsupported output type {output_type}")
        return output_type.model_validate(result.model_dump())
