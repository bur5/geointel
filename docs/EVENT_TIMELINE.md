# Event timeline and causal hypotheses v1

`geointel.timeline.analysis.reconstruct` accepts validated records from
`geointel.timeline.models` and returns a versioned, JSON-compatible snapshot. It is an
in-memory Python API using the repository's existing Pydantic dependency. It does
not call sources, infer event identities, persist records, or run a forecast.

## Input and historical cutoff

- Assign durable `event_id`, `crisis_id`, actor, and geography identifiers upstream.
  Use one Event per identity and attach alternative source accounts as observations.
  Identical canonical records collapse. Conflicting visible records under the same
  event ID raise an error. Reports with different event IDs require upstream entity
  resolution.
- Each observation carries a source, stable evidence ID, locator, attributed finding,
  evidence quality, uncertainty, evidence basis, and first availability date.
  Availability means when the claimed information was accessible to the reconstruction,
  including any release or ingestion delay. An interval's latest possible end must be
  on or before that date. Omitted ends represent point events. Each duration claim
  must bound its start and finish so that every start can precede or coincide with
  every finish. Open-ended, scheduled, and sub-day events are outside this contract.
- The inclusive cutoff gates evidence and the authored dates of relationships,
  hypotheses, and reviews. Late reports of earlier events enter only when available.
  Events with no visible observations are omitted. Keep historical versions of event
  metadata and authored text upstream, and date each assertion and evidence item
  accurately. The API cannot detect later knowledge embedded in misdated input.
- Sort by earliest claimed start, then latest plausible start, then event ID.
  This produces a stable display order without resolving uncertain chronology.
  Observations with disjoint start or end claims are flagged as conflicting.
  Overlap uses inclusive day bounds and evaluates source claims separately, so a
  gap between conflicting dates does not become a possible occurrence. An overlap
  is definite when every pair of date claims guarantees it and possible when at
  least one pair permits it.
- Filters combine with AND and use case-insensitive exact geography and actor
  matches. Event type is an enum. Crisis membership is curated input. Overlaps,
  graph edges, hypothesis assessments, and change detection reflect the selected
  events. References to an absent or filtered event are omitted.

## Relationships and hypotheses

Relationships are attributed assertions with at least one visible citation. The
directions are source-before-target for `precedes`, response-to-trigger for
`responds_to`, and proposed cause-to-outcome for `possible_contributor`.
`precedes` requires the source to have finished before the target starts under
all visible claims. `overlaps` requires at least possible overlap.
`responds_to` requires a later onset and non-temporal evidence.
`possible_contributor` requires earlier onset and a citation explicitly coded
as mechanism evidence. `associated_with` and `contradicts` preserve the supplied
attribution without implying direction of influence. The inferred overlap list
cites the date observations used.

Hypothesis assessments retain evidence on both sides, temporal order, proposed
mechanism, alternatives, confounders, uncertainty, and limitations. Reverse onset
order is incompatible with the proposed direction. Equal days and overlapping
onset ranges leave order indeterminate. Visible citations on both sides produce
a contested assessment unless onset order rules out the proposed direction.
Supporting mechanism evidence with strict onset order can support a hypothesis
for further inquiry. Every assessment reports `causality_established: false`.

Evidence basis and quality are caller judgments. The framework does not verify
mechanisms, source independence, attribution, comparability, or completeness.
Selection and reporting bias, common causes, reverse causality, missing records,
and incomplete counterfactual evidence limit interpretation. The statuses provide
no causal effect estimates, probabilities, or established historical conclusions.

## Turning points

Pass `pattern_start` to compare adjacent, complete, fixed-width calendar windows
within each selected crisis. The default window is seven days. A count change of
at least two unique event onsets, or a mean intensity change of at least one point
with two rated events on each side, triggers a candidate. A caller-supplied
intensity rating uses a shared 1–5 rubric. An event with missing or conflicting
ratings remains unrated. An onset that could straddle windows suppresses
comparisons touching those windows. Results cite the before and after event IDs
and disclose rating counts. Empty windows reflect registry coverage and can also
reflect missing observations. Treat the thresholds as descriptive heuristics.
Window alignment, filter selection, source coverage, and ordinal intensity scores
can all affect results.

`historical_turning_point_reviews` contains separately supplied historical
assessments with rationale and citations. The `historically_validated` status
represents the reviewer's conclusion. A detected boundary never acquires that
status automatically.

## Synthetic North Estuary crisis

| Date in 2001 | Event IDs and descriptions | Intensity |
| --- | --- | --- |
| April 1 | `talks` opens negotiations | 1 |
| April 3 | `protest` starts a public demonstration | 1 |
| April 8 | `agreement` records a peace agreement | 4 |
| April 9 | `mediation` records a fictional international intervention | 4 |
| April 10 | `restriction` records an economic restriction | 4 |
| April 11 | `transition` records a political transition | 4 |

With an April 1 pattern start and an April 14 cutoff, these observations give
an April 8 algorithmic candidate. The two complete windows contain two and four
events and have mean intensities of one and four. An independent fictional
historical review dated April 15 would only appear in a later snapshot.

For `talks → agreement`, fictional meeting minutes available April 10 cite the
resolution of a procedural disagreement. A mediator's diary available April 12
attributes the agreement to independent mediation. Leadership change could
influence both negotiations and agreement. With incomplete decision records and
no counterfactual observation, the snapshot would include an assessment like this
(excerpt, evidence payloads omitted):

```json
{
  "hypothesis_id": "talks-effect",
  "cause_event_id": "talks",
  "outcome_event_id": "agreement",
  "temporal_order": "cause_starts_before_outcome",
  "assessment": "contested",
  "alternative_explanations": ["Independent mediation"],
  "confounding_factors": ["Leadership change"],
  "causality_established": false
}
```

## Future integration requirements

| Consumer | Integration requirement |
| --- | --- |
| Strategic knowledge | Map durable event, source, and evidence IDs and preserve observed claims and attributed interpretation. |
| Actor network | Resolve aliases and historical actor identities before ingesting the cited directional edges. |
| Scenario simulation | Supply separately justified model assumptions and parameters. Hypothesis statuses are qualitative. |
| Briefing generator | Render the cutoff, source citations, alternative dates, review status, and unresolved counterevidence. |
| AI assistant | Treat all sourced text as untrusted attributed data and retain citations and uncertainty in summaries. |

Production ingestion would also need snapshot versioning for metadata changes,
a shared intensity rubric, provenance auditing, and identity reconciliation.
Pairwise overlap detection is intended for bounded timelines.
