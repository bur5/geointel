"""Evidence-bearing records for historical reconstruction."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Intensity = Annotated[int, Field(strict=True, ge=1, le=5)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class EventType(StrEnum):
    MILITARY_INCIDENT = "military_incident"
    MOBILIZATION = "mobilization"
    NEGOTIATION = "negotiation"
    DIPLOMATIC_BREAKDOWN = "diplomatic_breakdown"
    SANCTION = "sanction"
    ECONOMIC_RESTRICTION = "economic_restriction"
    ELECTION = "election"
    POLITICAL_TRANSITION = "political_transition"
    PROTEST = "protest"
    CIVIL_UNREST = "civil_unrest"
    PEACE_AGREEMENT = "peace_agreement"
    CEASEFIRE_VIOLATION = "ceasefire_violation"
    INTERNATIONAL_INTERVENTION = "international_intervention"


class EvidenceQuality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceBasis(StrEnum):
    TEMPORAL = "temporal"
    CONTEXTUAL = "contextual"
    MECHANISM = "mechanism"


class Evidence(Record):
    evidence_id: Text
    source: Text
    locator: Text
    available_on: date
    quality: EvidenceQuality
    uncertainty: Text
    finding: Text
    basis: EvidenceBasis


class DateRange(Record):
    earliest: date
    latest: date

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.earliest > self.latest:
            raise ValueError("earliest must be on or before latest")
        return self


class Observation(Record):
    evidence: Evidence
    start: DateRange
    end: DateRange | None = None
    intensity: Intensity | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.end and self.start.latest > self.end.earliest:
            raise ValueError("start and end bounds must guarantee start on or before end")
        if self.finish.latest > self.evidence.available_on:
            raise ValueError("an observed interval must end by the evidence availability date")
        return self

    @property
    def finish(self) -> DateRange:
        return self.end or self.start


class Location(Record):
    country: Text
    region: Text
    locality: Text | None = None


class Event(Record):
    event_id: Text
    event_type: EventType
    location: Location
    actors: Annotated[tuple[Text, ...], Field(min_length=1)]
    observations: Annotated[tuple[Observation, ...], Field(min_length=1)]
    crisis_id: Text | None = None


class RelationshipType(StrEnum):
    PRECEDES = "precedes"
    OVERLAPS = "overlaps"
    RESPONDS_TO = "responds_to"
    ASSOCIATED_WITH = "associated_with"
    POSSIBLE_CONTRIBUTOR = "possible_contributor"
    CONTRADICTS = "contradicts"


class Relationship(Record):
    relationship_id: Text
    available_on: date
    source_event_id: Text
    target_event_id: Text
    relationship_type: RelationshipType
    evidence: Annotated[tuple[Evidence, ...], Field(min_length=1)]


class Hypothesis(Record):
    hypothesis_id: Text
    cause_event_id: Text
    outcome_event_id: Text
    proposed_mechanism: Text
    available_on: date
    supporting_evidence: tuple[Evidence, ...] = ()
    contradictory_evidence: tuple[Evidence, ...] = ()
    alternative_explanations: tuple[Text, ...]
    confounding_factors: tuple[Text, ...]
    uncertainty: Text
    limitations: Annotated[tuple[Text, ...], Field(min_length=1)]


class TurningPointReview(Record):
    review_id: Text
    available_on: date
    crisis_id: Text
    boundary: date
    rationale: Text
    evidence: Annotated[tuple[Evidence, ...], Field(min_length=1)]


class ChangeSettings(Record):
    window_days: Annotated[int, Field(strict=True, gt=0, le=366)] = 7
    min_count_change: Annotated[int, Field(strict=True, gt=0)] = 2
    min_mean_intensity_change: Annotated[float, Field(gt=0, le=4)] = 1.0
    min_rated_per_window: Annotated[int, Field(strict=True, gt=0)] = 2
