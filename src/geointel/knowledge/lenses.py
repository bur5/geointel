from typing import Protocol

from geointel.domain.schemas import (
    Confidence,
    RetrievedStrategicClaim,
    StrategicLensContext,
    StrategicLensOutput,
)


class StrategicLens(Protocol):
    name: str
    version: str

    def analyze(
        self, context: StrategicLensContext, retrieved_knowledge: list[RetrievedStrategicClaim]
    ) -> StrategicLensOutput: ...


class LensRegistry:
    def __init__(self, lenses: list[StrategicLens] | None = None):
        self._lenses: dict[str, StrategicLens] = {}
        for lens in lenses or []:
            self.register(lens)

    def register(self, lens: StrategicLens) -> None:
        if lens.name in self._lenses:
            raise ValueError(f"lens already registered: {lens.name}")
        self._lenses[lens.name] = lens

    def all(self) -> list[StrategicLens]:
        return list(self._lenses.values())


class KissingerLens:
    """A restrained interpretive lens over retrieved attributed claims only."""

    name = "kissinger"
    version = "1.0"

    def analyze(self, context, retrieved_knowledge):
        ids = [claim.claim_id for claim in retrieved_knowledge]
        cases = sorted(
            {case for claim in retrieved_knowledge for case in claim.historical_case_ids}
        )
        if not retrieved_knowledge:
            return StrategicLensOutput(
                lens_name=self.name,
                lens_version=self.version,
                limitations=[
                    "The Kissinger lens is not informative for this question: no relevant "
                    "attributed claims were retrieved."
                ],
                counterarguments=[
                    "Other strategic theories and current empirical evidence must be considered "
                    "independently."
                ],
                unsupported_assumptions=[
                    "Balance, durable interests, alliance constraints, legitimacy, and diplomatic "
                    "off-ramps are not established by available knowledge."
                ],
            )
        interpretations = [
            f"Attributed claim {claim.claim_id} may frame questions of order, equilibrium, "
            "commitments, or diplomatic flexibility; it does not establish present facts or "
            "predict an outcome."
            for claim in retrieved_knowledge
        ]
        limitations = [
            "Historical analogy is interpretive: differences in actors, institutions, "
            "technology, geography, and time may defeat comparison.",
            "Famous-author status supplies no evidentiary weight and cannot override current data.",
            *[item for claim in retrieved_knowledge for item in claim.limitations],
        ]
        return StrategicLensOutput(
            lens_name=self.name,
            lens_version=self.version,
            interpretation=interpretations,
            claim_ids=ids,
            claim_provenance=[
                {"claim_id": x.claim_id, **x.provenance} for x in retrieved_knowledge
            ],
            applicability=[
                f"Retrieved for: {reason}"
                for x in retrieved_knowledge
                for reason in x.retrieval_reasons
            ],
            limitations=list(dict.fromkeys(limitations)),
            counterarguments=list(
                dict.fromkeys(
                    [
                        "Alternative theories may explain the same evidence differently.",
                        *[i for x in retrieved_knowledge for i in x.counterexamples],
                    ]
                )
            ),
            confidence=Confidence.LOW,
            unsupported_assumptions=[
                "The current balance of power, durable interests, credible commitments, "
                "legitimacy claims, and available off-ramps require empirical validation."
            ],
            historical_case_ids=cases,
        )


class NeutralAlternativeLens:
    """Minimal registration proof, not a substantive theory implementation."""

    name = "neutral-alternative"
    version = "0.1"

    def analyze(self, context, retrieved_knowledge):
        return StrategicLensOutput(
            lens_name=self.name,
            lens_version=self.version,
            claim_ids=[x.claim_id for x in retrieved_knowledge],
            claim_provenance=[
                {"claim_id": x.claim_id, **x.provenance} for x in retrieved_knowledge
            ],
            limitations=["Placeholder lens: no substantive interpretation is implemented."],
            counterarguments=["Compare multiple theories before drawing an inference."],
            unsupported_assumptions=["No causal assumptions were evaluated."],
        )
