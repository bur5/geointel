# Scenario Simulation v1

`geointel.scenarios` is an offline Python API for comparing hypothetical changes in conflict-risk
indicators. Each branch starts from the same dated baseline snapshot. The caller supplies every
event, assumption, change, provenance reference, and uncertainty note. Branches may reuse the
same event to represent a shared path before divergence. An empty event list gives a control.

## Units and transitions

- Use a case-sensitive `namespace:id` region key from one geographic scheme. All events must
  match the baseline key exactly. A scenario involving multiple territories can use an externally
  defined regional key covering the entire scenario.
- Supply a calendar date and a horizon of 1–3,660 days. Day 0 is the starting snapshot.
  Day 1 is the following calendar date. The last output is the start plus the full horizon.
- Scores are dimensionless integer points on an illustrative 0–10,000 scale. Define the
  direction and meaning of each indicator when preparing inputs. A positive delta increases
  that score. Each event delta must be between −10,000 and +10,000 points.
- For each indicator on each day, add all scheduled deltas to the preceding day's score and
  clamp once to the score range. Clipped excess is discarded and the step flags clipping.
  Days without changes carry the previous score forward. The comparison baseline is held
  constant at its starting values.
- Each branch reports daily scores, differences from baseline, applied event IDs, and the branch
  and event assumptions with their provenance and uncertainty. Compare branches on the same
  date and indicator. Branches and sensitivity requests follow caller order. Indicator names
  and applied event IDs are sorted within steps.
- Each sensitivity request replaces one event-indicator delta for one branch, reruns the branch,
  and reports the affected indicator's endpoint and change from its original endpoint. Supply
  multiple requests to try multiple values. Each request starts from the original branch.

Missing indicators, duplicate identifiers within their scope, invalid scores, mismatched regions,
and events outside the horizon raise validation errors. The Python API uses immutable input
models. Use `Scenario.model_validate_json(...)` to load saved JSON definitions, with ISO dates
and arrays. Record the rule version and all inputs, including sensitivity requests, to replay a
comparison. The engine reads no clocks, randomness, files, network, or database.

## Synthetic example

The fictional North Reach region starts at 4,500 tension points. All three branches assume a
border incident on day 1. Negotiations produce de-escalation in branch A. Branch B assumes
stalemate and no subsequent change. Branch C assumes a regional mobilization and further
escalation at an aggregate indicator level.

```python
from datetime import date

from geointel.scenarios import (
    Baseline,
    Branch,
    Change,
    Event,
    Indicator,
    Scenario,
    SensitivityInput,
    simulate,
)

region = "synthetic:north-reach"


def hypothetical(event_id, day, assumption, delta):
    return Event(
        id=event_id,
        region=region,
        day=day,
        assumption=assumption,
        changes=(Change(indicator="tension", delta=delta),),
        provenance=("synthetic:north-reach-v1",),
        uncertainty="The score change is an illustrative assumption.",
    )


incident = hypothetical("incident", 1, "A border incident raises tension.", 800)
talks = hypothetical("talks", 2, "Negotiations reduce tension.", -1400)
mobilization = hypothetical("mobilization", 2, "Regional mobilization raises tension.", 1600)

definition = Scenario(
    baseline=Baseline(
        region=region,
        start=date(2025, 1, 1),
        indicators=(Indicator(name="tension", score=4500),),
        provenance=("synthetic:north-reach-v1",),
        uncertainty="The starting score was chosen for this example.",
    ),
    horizon_days=3,
    branches=(
        Branch(name="A", assumption="Negotiations advance.", events=(incident, talks)),
        Branch(name="B", assumption="Stalemate persists.", events=(incident,)),
        Branch(name="C", assumption="Tensions escalate.", events=(incident, mobilization)),
    ),
)
result = simulate(
    definition,
    sensitivity=(
        SensitivityInput(branch="A", event_id="talks", indicator="tension", replacement_delta=-700),
    ),
)
```

| Branch | Day 0 | Day 1 | Day 2 | Day 3 | Day 3 change from baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| A · De-escalation | 4,500 | 5,300 | 3,900 | 3,900 | −600 |
| B · Prolonged instability | 4,500 | 5,300 | 5,300 | 5,300 | +800 |
| C · Further escalation | 4,500 | 5,300 | 6,900 | 6,900 | +2,400 |

With the negotiation change set to −700 points, A ends at 4,600, or 700 points above
its original endpoint.

## Scientific limits and future integrations

Scores are illustrative and have no calibrated link to conflict occurrence. The rules encode
caller assumptions and provide no causal effect estimates, empirical validation, likelihood
ranking, or statistical uncertainty intervals. Results depend on the selected scale, baseline,
event dates and assumed deltas. Clipping can hide the effect of larger changes. The engine has
no inferred feedback or cross-indicator interactions, and the constant control has no dynamics.

Potential integrations are caller-owned adapters.

- Forecasting requires an explicit mapping from a dated forecast snapshot into aligned
  indicators, with a defined transformation, resolution and provenance. Keep the original
  forecast and any probabilities in their native representation.
- Historical backtesting requires point-in-time inputs, aligned observations, a predeclared
  evaluation protocol, and safeguards against look-ahead bias. Replay alone establishes
  computational reproducibility.
- Early-warning signals require reviewed geographic and temporal mappings and explicit
  assumptions about how a signal would change an indicator. Preserve source references,
  coverage gaps, and disagreement.
- Assistant explanations can consume structured comparisons with their assumptions, event
  references, rule version, clipping flags, and limitations. Keep explanatory text tied to
  those inputs and label outputs as hypothetical.
