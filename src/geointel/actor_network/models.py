"""Input records and JSON-serializable results for an offline actor network."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ActorType(StrEnum):
    SOVEREIGN_STATE = "sovereign_state"
    INTERNATIONAL_ORGANIZATION = "international_organization"
    REGIONAL_ALLIANCE = "regional_alliance"
    GOVERNMENT = "government"
    NON_STATE_ARMED_GROUP = "non_state_armed_group"


class RelationshipType(StrEnum):
    ALLIANCE_MEMBERSHIP = "alliance_membership"
    DEFENSE_COOPERATION = "defense_cooperation"
    DIPLOMATIC_RELATIONS = "diplomatic_relations"
    ECONOMIC_DEPENDENCY = "economic_dependency"
    SANCTIONS = "sanctions"
    TERRITORIAL_DISPUTE = "territorial_dispute"
    ARMED_CONFLICT_INVOLVEMENT = "armed_conflict_involvement"


class EvidenceQuality(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RelationshipStatus(StrEnum):
    DOCUMENTED = "documented"
    TENTATIVE = "tentative"
    CONTESTED = "contested"
    REFUTED = "refuted"
    HYPOTHETICAL = "hypothetical"


class Validity(Record):
    start: date
    end: date | None = None

    @model_validator(mode="after")
    def check_order(self) -> Self:
        if self.end is not None and self.end <= self.start:
            raise ValueError("validity end must follow start")
        return self

    def includes(self, on: date) -> bool:
        return self.start <= on and (self.end is None or on < self.end)


class Source(Record):
    source_id: NonBlank
    citation: NonBlank
    quality: EvidenceQuality


class ExternalIdentifier(Record):
    namespace: NonBlank
    value: NonBlank


class ActorState(Record):
    name: NonBlank
    status: NonBlank
    validity: Validity


class Actor(Record):
    actor_id: NonBlank
    actor_type: ActorType
    states: tuple[ActorState, ...]
    external_ids: tuple[ExternalIdentifier, ...] = ()
    sources: tuple[Source, ...] = ()

    @model_validator(mode="after")
    def check_states_and_sources(self) -> Self:
        if not self.states:
            raise ValueError("at least one named actor state is required")
        states = sorted(self.states, key=lambda state: state.validity.start)
        for previous, current in zip(states, states[1:], strict=False):
            end = previous.validity.end
            if end is None or current.validity.start < end:
                raise ValueError("actor state periods must not overlap")
        if self.actor_type == ActorType.NON_STATE_ARMED_GROUP and not any(
            source.quality == EvidenceQuality.HIGH for source in self.sources
        ):
            raise ValueError("non-state armed groups require a high-quality source")
        return self

    def state_on(self, on: date) -> ActorState | None:
        return next((state for state in self.states if state.validity.includes(on)), None)


class RelationshipClaim(Record):
    claim_id: NonBlank
    source_actor_id: NonBlank
    target_actor_id: NonBlank
    relationship_type: RelationshipType
    validity: Validity
    provenance: Source
    uncertainty: NonBlank
    stance: Literal["supports", "refutes", "hypothetical"]
    region: NonBlank | None = None
    context_id: NonBlank | None = None

    @model_validator(mode="after")
    def check_endpoints(self) -> Self:
        if self.source_actor_id == self.target_actor_id:
            raise ValueError("a relationship requires distinct actors")
        if self.relationship_type == RelationshipType.ARMED_CONFLICT_INVOLVEMENT:
            if self.region is None or self.context_id is None:
                raise ValueError("armed conflict claims require a region and conflict context ID")
        return self


class Relationship(Record):
    source_actor_id: NonBlank
    target_actor_id: NonBlank
    relationship_type: RelationshipType
    region: NonBlank | None
    context_id: NonBlank | None
    status: RelationshipStatus
    claims: tuple[RelationshipClaim, ...]


class RelationshipPath(Record):
    on: date
    actor_ids: tuple[str, ...]
    relationships: tuple[Relationship, ...]


class CrisisScenario(Record):
    scenario_id: NonBlank
    region: NonBlank
    seed_actor_ids: tuple[NonBlank, ...]
    on: date

    @model_validator(mode="after")
    def check_seeds(self) -> Self:
        if not self.seed_actor_ids or len(set(self.seed_actor_ids)) != len(self.seed_actor_ids):
            raise ValueError("a crisis scenario requires unique seed actors")
        return self


class CrisisExposure(Record):
    scenario: CrisisScenario
    paths: tuple[RelationshipPath, ...]
    interpretation: Literal["documented_network_connectivity_only"] = (
        "documented_network_connectivity_only"
    )


class EconomicExposure(Record):
    actor_id: NonBlank
    on: date
    upstream_dependencies: tuple[RelationshipPath, ...]
    downstream_dependents: tuple[RelationshipPath, ...]


class MultiConflictConnection(Record):
    actor_id: NonBlank
    relationships: tuple[Relationship, ...]
