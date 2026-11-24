"""Resolve actors and traverse dated relationships with retained provenance."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Iterator
from datetime import date
from types import MappingProxyType
from typing import Literal

from .models import (
    Actor,
    CrisisExposure,
    CrisisScenario,
    EconomicExposure,
    EvidenceQuality,
    MultiConflictConnection,
    Relationship,
    RelationshipClaim,
    RelationshipPath,
    RelationshipStatus,
    RelationshipType,
)

Direction = Literal["both", "outgoing", "incoming"]
RelationshipKey = tuple[str, str, RelationshipType, str | None, str | None]

SYMMETRIC = frozenset(
    {
        RelationshipType.DEFENSE_COOPERATION,
        RelationshipType.DIPLOMATIC_RELATIONS,
        RelationshipType.TERRITORIAL_DISPUTE,
        RelationshipType.ARMED_CONFLICT_INVOLVEMENT,
    }
)


def _relationship_key(claim: RelationshipClaim) -> RelationshipKey:
    source, target = claim.source_actor_id, claim.target_actor_id
    if claim.relationship_type in SYMMETRIC:
        source, target = sorted((source, target))
    return source, target, claim.relationship_type, claim.region, claim.context_id


def _status(claims: tuple[RelationshipClaim, ...]) -> RelationshipStatus:
    support = [claim for claim in claims if claim.stance == "supports"]
    refuted = any(claim.stance == "refutes" for claim in claims)
    if support and refuted:
        return RelationshipStatus.CONTESTED
    if refuted:
        return RelationshipStatus.REFUTED
    if not support:
        return RelationshipStatus.HYPOTHETICAL
    if all(claim.provenance.quality == EvidenceQuality.LOW for claim in support):
        return RelationshipStatus.TENTATIVE
    return RelationshipStatus.DOCUMENTED


class ActorNetwork:
    """Immutable input records indexed by canonical and external identifiers."""

    def __init__(self, actors: Iterable[Actor], claims: Iterable[RelationshipClaim]) -> None:
        actor_index: dict[str, Actor] = {}
        external_index: dict[tuple[str, str], str] = {}
        for actor in actors:
            if actor.actor_id in actor_index:
                raise ValueError(f"duplicate actor ID: {actor.actor_id}")
            actor_index[actor.actor_id] = actor
            for external in actor.external_ids:
                key = (external.namespace, external.value)
                if key in external_index:
                    raise ValueError(f"duplicate external identifier: {key}")
                external_index[key] = actor.actor_id

        claim_index: dict[str, RelationshipClaim] = {}
        for claim in claims:
            if claim.claim_id in claim_index:
                raise ValueError(f"duplicate claim ID: {claim.claim_id}")
            for actor_id in (claim.source_actor_id, claim.target_actor_id):
                if actor_id not in actor_index:
                    raise ValueError(f"unknown actor in claim {claim.claim_id}: {actor_id}")
            claim_index[claim.claim_id] = claim

        self._actors = MappingProxyType(actor_index)
        self._external = MappingProxyType(external_index)
        self._claims = tuple(claim_index[key] for key in sorted(claim_index))

    def actor(self, actor_id: str) -> Actor:
        return self._actors[actor_id]

    def resolve_external(self, namespace: str, value: str) -> Actor:
        return self.actor(self._external[namespace, value])

    def resolve_name(self, name: str, *, on: date) -> Actor:
        """Resolve an exact, case-insensitive name at the supplied date."""
        requested = name.strip().casefold()
        matches = [
            actor
            for actor in self._actors.values()
            if (state := actor.state_on(on)) is not None and state.name.casefold() == requested
        ]
        if not matches:
            raise KeyError(name)
        if len(matches) > 1:
            raise ValueError(f"ambiguous actor name on {on}: {name}")
        return matches[0]

    def snapshot(self, on: date) -> NetworkSnapshot:
        """Group active claims by relationship identity at one explicit date."""
        groups: dict[RelationshipKey, list[RelationshipClaim]] = defaultdict(list)
        for claim in self._claims:
            if claim.validity.includes(on):
                groups[_relationship_key(claim)].append(claim)

        relationships = []
        for key in sorted(groups, key=lambda key: (*key[:3], key[3] or "", key[4] or "")):
            source, target, kind, region, context = key
            claims = tuple(groups[key])
            relationships.append(
                Relationship(
                    source_actor_id=source,
                    target_actor_id=target,
                    relationship_type=kind,
                    region=region,
                    context_id=context,
                    status=_status(claims),
                    claims=claims,
                )
            )
        return NetworkSnapshot(self, on, tuple(relationships))


class NetworkSnapshot:
    """Read-only relationship queries at a fixed date."""

    def __init__(
        self, network: ActorNetwork, on: date, relationships: tuple[Relationship, ...]
    ) -> None:
        self._network = network
        self._on = on
        self._relationships = relationships
        adjacency: dict[str, list[Relationship]] = defaultdict(list)
        for relationship in relationships:
            adjacency[relationship.source_actor_id].append(relationship)
            adjacency[relationship.target_actor_id].append(relationship)
        self._adjacency = MappingProxyType({key: tuple(value) for key, value in adjacency.items()})

    def relationships(
        self,
        *,
        actor_id: str | None = None,
        other_actor_id: str | None = None,
        types: Iterable[RelationshipType] | None = None,
        region: str | None = None,
    ) -> tuple[Relationship, ...]:
        """Return active records, including contested and hypothetical claims."""
        if actor_id is not None:
            self._network.actor(actor_id)
        if other_actor_id is not None:
            self._network.actor(other_actor_id)
            if actor_id is None:
                raise ValueError("other_actor_id requires actor_id")
        if actor_id is not None and other_actor_id == actor_id:
            return ()
        records = self._relationships if actor_id is None else self._adjacency.get(actor_id, ())
        kinds = None if types is None else frozenset(types)
        return tuple(
            record
            for record in records
            if (kinds is None or record.relationship_type in kinds)
            and (region is None or record.region == region)
            and (
                other_actor_id is None
                or other_actor_id in (record.source_actor_id, record.target_actor_id)
            )
        )

    def _paths(
        self,
        seeds: tuple[str, ...],
        max_hops: int,
        types: Iterable[RelationshipType] | None,
        direction: Direction,
        target: str | None = None,
    ) -> Iterator[RelationshipPath]:
        if type(max_hops) is not int or max_hops < 0:
            raise ValueError("max_hops must be a nonnegative integer")
        if direction not in ("both", "outgoing", "incoming"):
            raise ValueError("invalid traversal direction")
        for actor_id in seeds:
            self._network.actor(actor_id)
        kinds = None if types is None else frozenset(types)
        parents: dict[str, tuple[str, Relationship] | None] = dict.fromkeys(seeds)
        queue = deque((actor_id, 0) for actor_id in sorted(seeds))
        while queue:
            actor_id, depth = queue.popleft()
            if actor_id == target or (target is None and depth > 0):
                actors = [actor_id]
                relationships = []
                while (parent := parents[actors[-1]]) is not None:
                    previous, relationship = parent
                    actors.append(previous)
                    relationships.append(relationship)
                yield RelationshipPath(
                    on=self._on,
                    actor_ids=tuple(reversed(actors)),
                    relationships=tuple(reversed(relationships)),
                )
                if target is not None:
                    return
            if depth >= max_hops:
                continue
            for relationship in self._adjacency.get(actor_id, ()):
                if relationship.status != RelationshipStatus.DOCUMENTED:
                    continue
                kind = relationship.relationship_type
                if kinds is not None and kind not in kinds:
                    continue
                source, destination = relationship.source_actor_id, relationship.target_actor_id
                forward = actor_id == source
                if kind not in SYMMETRIC and (
                    (direction == "incoming" and forward)
                    or (direction == "outgoing" and not forward)
                ):
                    continue
                neighbor = destination if forward else source
                if neighbor not in parents:
                    parents[neighbor] = actor_id, relationship
                    queue.append((neighbor, depth + 1))

    def connected_actors(
        self,
        actor_id: str,
        *,
        max_hops: int = 3,
        types: Iterable[RelationshipType] | None = None,
        direction: Direction = "both",
    ) -> tuple[RelationshipPath, ...]:
        """Return one shortest documented path per reachable actor, excluding the origin."""
        return tuple(self._paths((actor_id,), max_hops, types, direction))

    def shortest_path(
        self,
        actor_id: str,
        other_actor_id: str,
        *,
        max_hops: int = 3,
        types: Iterable[RelationshipType] | None = None,
        direction: Direction = "both",
    ) -> RelationshipPath | None:
        self._network.actor(other_actor_id)
        return next(
            self._paths((actor_id,), max_hops, types, direction, target=other_actor_id), None
        )

    def economic_exposure(self, actor_id: str, *, max_hops: int = 3) -> EconomicExposure:
        """Follow dependency claims in both directions, retaining directional paths."""
        types = (RelationshipType.ECONOMIC_DEPENDENCY,)
        return EconomicExposure(
            actor_id=actor_id,
            on=self._on,
            upstream_dependencies=self.connected_actors(
                actor_id, max_hops=max_hops, types=types, direction="outgoing"
            ),
            downstream_dependents=self.connected_actors(
                actor_id, max_hops=max_hops, types=types, direction="incoming"
            ),
        )

    def multi_conflict_connections(self) -> tuple[MultiConflictConnection, ...]:
        """Return actors with documented links to two or more distinct conflict IDs."""
        by_actor: dict[str, list[Relationship]] = defaultdict(list)
        for relationship in self._relationships:
            if (
                relationship.relationship_type == RelationshipType.ARMED_CONFLICT_INVOLVEMENT
                and relationship.status == RelationshipStatus.DOCUMENTED
            ):
                by_actor[relationship.source_actor_id].append(relationship)
                by_actor[relationship.target_actor_id].append(relationship)
        return tuple(
            MultiConflictConnection(actor_id=actor_id, relationships=tuple(records))
            for actor_id, records in sorted(by_actor.items())
            if len({record.context_id for record in records}) >= 2
        )

    def crisis_exposure(
        self,
        scenario: CrisisScenario,
        *,
        max_hops: int = 3,
        types: Iterable[RelationshipType] | None = None,
    ) -> CrisisExposure:
        """Find potential connections from explicitly supplied scenario participants."""
        if scenario.on != self._on:
            raise ValueError("crisis scenario date must match the snapshot date")
        return CrisisExposure(
            scenario=scenario,
            paths=tuple(self._paths(scenario.seed_actor_ids, max_hops, types, "both")),
        )
