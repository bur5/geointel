# Geopolitical actor network v1

`geointel.actor_network` is an offline, in-memory Python module. Callers supply actor records and
relationship claims. The module performs no network requests or database writes and uses an
explicit date for every relationship snapshot.

## Records and evidence

- Assign one stable ID per actor. Use nonoverlapping actor states for historical names and statuses.
  A date before or between state records has no known state. Name lookup uses exact case-folded
  matching and fails on ambiguity. External identifiers are exact, namespaced and unique across
  the registry. They are undated in v1.
- A government and its state may have separate IDs. Actor type stays fixed for a given ID.
  Non-state armed groups require at least one source rated high by the input curator.
- Actor states and claims use half-open date intervals, with an inclusive start and an exclusive
  end. An omitted end leaves the record open. Claim validity governs the graph. Actor state
  metadata provides historical identity and status independently of claim validity.
- Every claim includes a source ID, citation, curator-assigned quality, stance and explicit
  uncertainty. Citation text is inert. Each claim retains its own validity and provenance in
  query output.
- The relationship key consists of the endpoints, relationship type, optional region and optional
  context ID. Defense cooperation, diplomatic relations, territorial disputes and conflict
  involvement are symmetric. Alliance membership runs from member to alliance, economic dependency
  from dependent to supplier, and sanctions from issuer to target.
- A relationship is documented if active support includes medium- or high-quality evidence and
  there is no active refutation. Support exclusively from low-quality evidence is tentative.
  Overlapping support and refutation make the relationship contested regardless of source quality.
  Refutation alone yields refuted status. Hypothetical claims stay visible with their own stance
  and never affect the classification of other claims. A relationship with only hypothetical
  claims is hypothetical. Direct queries expose all statuses.
- Conflict involvement links two actors documented as involved in the same conflict. Each claim
  requires a region and a stable conflict context ID. Repeated claims and several regions for
  the same conflict count as one conflict in multi-conflict discovery.

## Synthetic example

```python
from datetime import date

from geointel.actor_network import (
    Actor,
    ActorNetwork,
    ActorState,
    CrisisScenario,
    RelationshipClaim,
    RelationshipType,
    Source,
    Validity,
)

on = date(2025, 1, 1)
validity = Validity(start=on)
actors = [
    Actor(
        actor_id=actor_id,
        actor_type="sovereign_state",
        states=(ActorState(name=name, status="active", validity=validity),),
    )
    for actor_id, name in [("a", "Synthetic A"), ("b", "Synthetic B"), ("c", "Synthetic C")]
]
claims = [
    RelationshipClaim(
        claim_id=claim_id,
        source_actor_id=dependent,
        target_actor_id=supplier,
        relationship_type=RelationshipType.ECONOMIC_DEPENDENCY,
        validity=validity,
        provenance=Source(
            source_id=claim_id, citation=f"Synthetic record {claim_id}", quality="high"
        ),
        uncertainty="The dependency's magnitude is unknown.",
        stance="supports",
    )
    for claim_id, dependent, supplier in [("ab", "a", "b"), ("bc", "b", "c")]
]
snapshot = ActorNetwork(actors, claims).snapshot(on)

direct = snapshot.relationships(
    actor_id="a", other_actor_id="b", types=[RelationshipType.ECONOMIC_DEPENDENCY]
)
assert direct[0].claims[0].provenance.source_id == "ab"

indirect = snapshot.shortest_path("a", "c", direction="outgoing")
assert indirect.actor_ids == ("a", "b", "c")

exposure = snapshot.economic_exposure("b")
assert exposure.downstream_dependents[0].actor_ids == ("b", "a")

scenario = CrisisScenario(scenario_id="synthetic-west", region="west", seed_actor_ids=("a",), on=on)
result = snapshot.crisis_exposure(scenario, max_hops=2)
assert [path.actor_ids for path in result.paths] == [("a", "b"), ("a", "b", "c")]
payload = result.model_dump(mode="json")
```

`connected_actors` returns one shortest documented path per reachable actor. It defaults to three
hops and can filter relationship types or follow a specific direction. Ties follow sorted seed
IDs and stable relationship ordering. `multi_conflict_connections` returns actors with documented
direct links to at least two distinct conflicts, along with the supporting relationship records.

Crisis analysis starts from explicitly supplied seed actors. The region labels the scenario.
Paths may extend across regions through documented relationships. Each path starts at a closest
seed and includes the relationship records and claims for every hop. This is an exposure screen.
It supplies no forecast, intervention probability or conclusion about future participation.

## Performance and integration

- Network construction indexes IDs and sorts claims once. Each snapshot scans all claims,
  groups active claims, sorts the relationship keys and builds an adjacency index. Reuse a
  snapshot for multiple queries on the same date. Name lookup scans the registry and actor states.
- Breadth-first traversal uses time proportional to the explored vertices and indexed edges,
  plus the size of the paths returned. It keeps one predecessor per visited actor. Returning every
  path along a long chain can still take quadratic space in the number of actors. The hop limit
  bounds depth. Dense snapshots may still reach many actors within that limit.
- The evidence policy works on caller-supplied ratings and matching keys. It does not verify
  sources, infer independence, reconcile conflicting region identifiers, detect renamed conflicts,
  quantify dependencies or model causal propagation. Snapshot dates represent claim validity,
  so forecasting callers must supply an evidence cutoff separately to avoid look-ahead bias.
- Consumers can serialize results with `model_dump(mode="json")` or `model_dump_json()`. Before
  connecting to forecasting, scenario simulation or assistant workflows, define a versioned
  interchange contract, curate canonical actor and conflict IDs and region mappings, establish
  source qualification and evidence cutoffs, and define which relationship types and directions
  are relevant to each use case. Assistant displays should carry the original citations,
  uncertainty and scenario interpretation. Forecasting requires independent validation of any
  proposed use of relationship data.
