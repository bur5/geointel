from typing import TypeVar

from pydantic import BaseModel

from geointel.domain.schemas import (
    AnalystOutput,
    Confidence,
    ConflictType,
    ForecastOutput,
    RedTeamOutput,
    RiskAssessment,
    SynthesisOutput,
)

T = TypeVar("T", bound=BaseModel)


class OfflineModel:
    """Deterministic, explicitly non-live model for reproducible development—not intelligence."""

    name = "offline-rules-v1"

    def generate(self, role: str, payload: dict, output_type: type[T]) -> T:
        evidence = payload.get("evidence", [])
        signals = payload.get("predictive_signals", [])
        metadata = payload.get("collection_metadata", {})
        if output_type is AnalystOutput:
            result = AnalystOutput(
                observed_evidence=[e["summary"] for e in evidence],
                predictive_signals=[
                    (
                        f"VIEWS model output {item['source_record_id']} for "
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
                historical_base_rate_notes=[
                    "No validated historical base-rate dataset was available in offline mode."
                ],
                assumptions=[
                    "Absence of retrieved evidence is not evidence of absence.",
                    "Offline mode uses no current-events feed.",
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
                            "Insufficient validated evidence to quantify risk in offline mode."
                        ),
                        evidence_for=[],
                        evidence_against=[],
                        unknowns=["Current events and historical base rates are unavailable."],
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
                missing_evidence=["No live current-events or validated base-rate dataset."],
                unjustified_precision=[
                    "Do not assign numeric probabilities without calibrated data."
                ],
                false_positive_risks=[
                    "Political tension must not be conflated with organized violence."
                ],
                predictive_signal_concerns=(
                    [
                        "VIEWS output is a predictive model signal, not observed factual evidence; "
                        "do not convert its value into a GEOINTEL probability."
                    ]
                    if signals
                    else ["No VIEWS predictive signal was available."]
                ),
                geographic_mismatches=[x for x in mismatch_notes if "geographic" in x],
                horizon_mismatches=[x for x in mismatch_notes if "horizon" in x],
            )
        elif output_type is SynthesisOutput:
            critique = payload["red_team"]
            result = SynthesisOutput(
                summary=(
                    "Insufficient evidence for quantified risk. The red-team review requires "
                    "restraint and additional independent data."
                ),
                assessments=[
                    RiskAssessment.model_validate(x) for x in payload["forecast"]["assessments"]
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
