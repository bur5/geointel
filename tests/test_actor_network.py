import json
from datetime import date

import pytest
from pydantic import ValidationError

from geointel.actor_network import (
    Actor,
    ActorNetwork,
    ActorState,
    ActorType,
    CrisisScenario,
    EvidenceQuality,
    ExternalIdentifier,
    RelationshipClaim,
    RelationshipStatus,
    RelationshipType,
    Source,
    Validity,
)

START = date(2000, 1, 1)
CHANGE = date(2010, 1, 1)
BEFORE_CHANGE = date(2009, 12, 31)
OPEN = Validity(start=START)
SOURCE = Source(
    source_id="synthetic-1", citation="Synthetic record 1", quality=EvidenceQuality.HIGH
)
COUNTERSOURCE = Source(
    source_id="synthetic-2", citation="Synthetic record 2", quality=EvidenceQuality.MEDIUM
)


def actor(actor_id, **fields):
    defaults = {
        "actor_type": ActorType.SOVEREIGN_STATE,
        "states": (ActorState(name=f"Synthetic {actor_id}", status="active", validity=OPEN),),
    }
    return Actor(actor_id=actor_id, **(defaults | fields))


def claim(claim_id, source, target, **fields):
    defaults = {
        "relationship_type": RelationshipType.DEFENSE_COOPERATION,
        "validity": OPEN,
        "provenance": SOURCE,
        "uncertainty": "Scope of the synthetic agreement is incomplete.",
        "stance": "supports",
    }
    return RelationshipClaim(
        claim_id=claim_id,
        source_actor_id=source,
        target_actor_id=target,
        **(defaults | fields),
    )


def test_resolves_stable_identity_across_name_and_status_changes():
    external_id = ExternalIdentifier(namespace="synthetic", value="alpha")
    old = ActorState(name="Old Alpha", status="active", validity=Validity(start=START, end=CHANGE))
    new = ActorState(name="New Alpha", status="transitional", validity=Validity(start=CHANGE))
    alpha = actor("a", states=(new, old), external_ids=(external_id,))
    network = ActorNetwork([alpha, actor("b")], [])

    assert network.actor("a") is alpha
    assert network.resolve_external("synthetic", "alpha") == alpha
    assert network.resolve_name(" OLD ALPHA ", on=BEFORE_CHANGE) == alpha
    assert network.resolve_name("new alpha", on=CHANGE).state_on(CHANGE).status == "transitional"
    with pytest.raises(KeyError):
        network.resolve_name("Old Alpha", on=CHANGE)
    with pytest.raises(ValueError, match="ambiguous actor name"):
        ActorNetwork([alpha, actor("b", states=(old,))], []).resolve_name("Old Alpha", on=START)
    with pytest.raises(ValidationError, match="must not overlap"):
        actor("bad", states=(new, new))


def test_duplicate_identities_and_claims_are_rejected():
    external_id = ExternalIdentifier(namespace="synthetic", value="1")
    alpha = actor("a", external_ids=(external_id,))
    beta = actor("b", external_ids=(external_id,))
    with pytest.raises(ValueError, match="duplicate actor ID"):
        ActorNetwork([alpha, alpha], [])
    with pytest.raises(ValueError, match="duplicate external identifier"):
        ActorNetwork([alpha, beta], [])
    link = claim("link", "a", "b")
    with pytest.raises(ValueError, match="duplicate claim ID"):
        ActorNetwork([alpha, actor("b")], [link, link])


def test_invalid_references_fail_instead_of_disappearing():
    with pytest.raises(ValueError, match="unknown actor in claim"):
        ActorNetwork([actor("a")], [claim("invalid", "a", "b")])
    snapshot = ActorNetwork([actor("a")], []).snapshot(START)
    with pytest.raises(KeyError):
        snapshot.shortest_path("a", "b")
    with pytest.raises(KeyError):
        snapshot.crisis_exposure(
            CrisisScenario(scenario_id="test", region="west", seed_actor_ids=("b",), on=START)
        )


def test_requires_provenance_and_uncertainty_and_reliable_armed_group_source():
    payload = claim("x", "a", "b").model_dump()
    del payload["provenance"]
    with pytest.raises(ValidationError, match="provenance"):
        RelationshipClaim.model_validate(payload)
    with pytest.raises(ValidationError, match="citation"):
        Source(source_id="x", citation=" ", quality=EvidenceQuality.HIGH)
    with pytest.raises(ValidationError, match="uncertainty"):
        claim("y", "a", "b", uncertainty=" ")
    with pytest.raises(ValidationError, match="high-quality source"):
        actor("group", actor_type=ActorType.NON_STATE_ARMED_GROUP, sources=(COUNTERSOURCE,))
    group = actor("group", actor_type=ActorType.NON_STATE_ARMED_GROUP, sources=(SOURCE,))
    assert group.sources == (SOURCE,)


def test_date_type_and_region_filters_across_relationship_change():
    old = claim("old", "a", "b", validity=Validity(start=START, end=CHANGE), region="west")
    new = claim(
        "new",
        "a",
        "b",
        validity=Validity(start=CHANGE),
        relationship_type=RelationshipType.SANCTIONS,
    )
    network = ActorNetwork([actor("a"), actor("b")], [new, old])
    assert network.snapshot(BEFORE_CHANGE).relationships(region="west")[0].claims == (old,)
    assert network.snapshot(CHANGE).relationships(region="west") == ()
    assert network.snapshot(CHANGE).relationships(actor_id="b", other_actor_id="a")[0].claims == (
        new,
    )
    assert (
        network.snapshot(CHANGE).relationships(types=[RelationshipType.DEFENSE_COOPERATION]) == ()
    )
    assert network.snapshot(date(1999, 12, 31)).relationships() == ()
    with pytest.raises(ValidationError, match="end must follow start"):
        Validity(start=START, end=START)


def test_conflicting_evidence_stays_visible_and_cannot_drive_traversal():
    positive = claim("positive", "a", "b")
    negative = claim(
        "negative",
        "b",
        "a",
        stance="refutes",
        provenance=COUNTERSOURCE,
        validity=Validity(start=CHANGE),
    )
    hypothetical = claim("scenario", "b", "c", stance="hypothetical")
    weak = SOURCE.model_copy(update={"quality": EvidenceQuality.LOW})
    tentative = claim("weak", "a", "c", provenance=weak)
    refuted = claim("refuted", "a", "d", stance="refutes")
    network = ActorNetwork(
        [actor(key) for key in "abcd"], [positive, negative, hypothetical, tentative, refuted]
    )

    assert network.snapshot(BEFORE_CHANGE).shortest_path("a", "b").actor_ids == ("a", "b")
    snapshot = network.snapshot(CHANGE)
    contested = snapshot.relationships(actor_id="a", other_actor_id="b")[0]
    assert contested.status == RelationshipStatus.CONTESTED
    assert contested.claims == (negative, positive)
    assert {item.status for item in snapshot.relationships()} == {
        RelationshipStatus.CONTESTED,
        RelationshipStatus.HYPOTHETICAL,
        RelationshipStatus.TENTATIVE,
        RelationshipStatus.REFUTED,
    }
    assert snapshot.connected_actors("a") == ()


def test_indirect_discovery_handles_cycles_and_breaks_ties_deterministically():
    actors = [actor(key) for key in "abcde"]
    claims = [
        claim("ab", "a", "b"),
        claim("ac", "a", "c"),
        claim("bd", "b", "d"),
        claim("cd", "c", "d"),
    ]
    network = ActorNetwork(actors, claims).snapshot(START)
    reversed_network = ActorNetwork(reversed(actors), reversed(claims)).snapshot(START)

    paths = network.connected_actors("a")
    assert paths == reversed_network.connected_actors("a")
    assert [path.actor_ids for path in paths] == [("a", "b"), ("a", "c"), ("a", "b", "d")]
    assert network.shortest_path("a", "d") == paths[-1]
    assert network.shortest_path("a", "d", max_hops=1) is None
    assert network.shortest_path("a", "e") is None
    assert network.connected_actors("a", types=[RelationshipType.SANCTIONS]) == ()


def test_directional_economic_exposure():
    kind = RelationshipType.ECONOMIC_DEPENDENCY
    links = [
        claim("ab", "a", "b", relationship_type=kind),
        claim("bc", "b", "c", relationship_type=kind),
        claim("cd", "c", "d"),
    ]
    snapshot = ActorNetwork([actor(key) for key in "abcd"], links).snapshot(START)

    exposure = snapshot.economic_exposure("b")
    assert [path.actor_ids for path in exposure.upstream_dependencies] == [("b", "c")]
    assert [path.actor_ids for path in exposure.downstream_dependents] == [("b", "a")]
    assert snapshot.shortest_path("c", "a", direction="outgoing") is None
    assert snapshot.shortest_path("c", "a", direction="incoming").actor_ids == ("c", "b", "a")


def test_multi_conflict_connections_count_conflicts_not_citations_or_regions():
    kind = RelationshipType.ARMED_CONFLICT_INVOLVEMENT
    links = [
        claim("west", "a", "b", relationship_type=kind, region="west", context_id="war-1"),
        claim("also-west", "a", "b", relationship_type=kind, region="west", context_id="war-1"),
        claim("cross-border", "a", "b", relationship_type=kind, region="south", context_id="war-1"),
        claim("east", "a", "c", relationship_type=kind, region="east", context_id="war-2"),
    ]
    snapshot = ActorNetwork([actor(key) for key in "abc"], links).snapshot(START)
    (result,) = snapshot.multi_conflict_connections()
    assert result.actor_id == "a"
    assert {link.context_id for link in result.relationships} == {"war-1", "war-2"}
    with pytest.raises(ValidationError, match="conflict context ID"):
        claim("missing-region", "a", "b", relationship_type=kind)


def test_crisis_uses_explicit_seeds_and_documented_paths_with_json_provenance():
    actors = [actor(key) for key in "abcdef"]
    links = [
        claim("ab", "a", "b"),
        claim("ec", "e", "c"),
        claim("bc", "b", "c", region="outside-scenario"),
        claim("cd", "c", "d", region="west", stance="hypothetical"),
        claim("bf", "b", "f", region="outside-scenario"),
    ]
    snapshot = ActorNetwork(actors, links).snapshot(START)
    scenario = CrisisScenario(
        scenario_id="test", region="west", seed_actor_ids=("e", "a"), on=START
    )

    result = snapshot.crisis_exposure(scenario)
    payload = json.loads(result.model_dump_json())
    assert payload["scenario"]["on"] == "2000-01-01"
    assert payload["interpretation"] == "documented_network_connectivity_only"
    assert [path["actor_ids"] for path in payload["paths"]] == [
        ["a", "b"],
        ["e", "c"],
        ["a", "b", "f"],
    ]
    first_claim = payload["paths"][0]["relationships"][0]["claims"][0]
    assert first_claim["provenance"]["source_id"] == "synthetic-1"
    assert first_claim["uncertainty"]
    with pytest.raises(ValueError, match="snapshot date"):
        snapshot.crisis_exposure(scenario.model_copy(update={"on": CHANGE}))


def test_large_synthetic_network_is_iterative_and_respects_hop_limits():
    size = 6000
    actors = (actor(str(index)) for index in range(size))
    claims = (claim(f"link-{index}", str(index), str((index + 1) % size)) for index in range(size))
    snapshot = ActorNetwork(actors, claims).snapshot(START)

    assert len(snapshot.relationships()) == size
    assert len(snapshot.connected_actors("0", max_hops=10)) == 20
    path = snapshot.shortest_path("0", "3000", max_hops=3000)
    assert path.actor_ids[0] == "0"
    assert path.actor_ids[-1] == "3000"
    assert len(path.relationships) == 3000
