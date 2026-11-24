# Historical forecast validation protocol

## Repository audit

Audited main at `aaf887030e39a0960323096a7075be783aa97bdf` and the open PR
heads listed below. The foundation runs on that main without importing their code.

| Component | Available work and boundary |
| --- | --- |
| Main forecasting and domain | [Immutable Forecast and ForecastSignal](../src/geointel/domain/models.py) records preserve assessments and provider-native values. The [forecasting contract](FORECASTING.md) requires calibrated justification for numeric output. Qualitative output, ranges and confidence labels have no point-probability mapping. |
| Main ingestion and historical features | [UCDP/ACLED and VIEWS/CAST adapters](../src/geointel/connectors) provide normalized observations and external signals. [Historical summaries](HISTORICAL_BASE_RATES.md) capture coverage and counts. They supply neither a complete exposure denominator nor an independently verified vintage archive. |
| Main evaluation | [Validation](VALIDATION.md) checks offline behavioral invariants. [Monitoring](MONITORING.md) checks comparable transitions and alert lifecycle. Empirical accuracy, calibration and incident-level detection remain unmeasured. |
| [#24](https://github.com/bur5/geointel/pull/24), `d296ee7` | Historical conflict profiles, eligibility/taxonomy review. Reuse approved definitions after integration. Profile counts alone cannot estimate prospective probabilities. |
| [#25](https://github.com/bur5/geointel/pull/25), `ef41b7d` | Pending governance corrections. Owner approval and existing repository governance remain outside this work. |
| [#33](https://github.com/bur5/geointel/pull/33), `904bb1b` | Run-level source quality and freshness diagnostics. Use for operational diagnostics once available. Retrieval and freshness clocks cannot establish historical publication or completeness. |
| [#34](https://github.com/bur5/geointel/pull/34), `ea585b3` | Owns offline panel and scoring schemas, per-row forecast/outcome eligibility, Brier, log loss, reliability bins, threshold metrics, count MAE and exact matched intersections. Defer duplicate scorer, scoring CLI, score fixtures and baseline input adapter. This branch supplies fold lineage checks and discrimination metrics. Baseline fitting and interval estimation remain separate work. |
| [#35](https://github.com/bur5/geointel/pull/35), `d10c93e`, and [#37](https://github.com/bur5/geointel/pull/37), `639d7e2` | Alternative advisory implementations touch the same module. Their thresholds and transition semantics differ. Select the reviewed contract before defining an adapter or alert replay harness. Any interval-midpoint adapter is ineligible for binary probability scoring without a separately justified probability model. |
| [#40](https://github.com/bur5/geointel/pull/40), [#41](https://github.com/bur5/geointel/pull/41), [#42](https://github.com/bur5/geointel/pull/42) | Timeline reconstruction, cutoff-aware search and read-only dashboard views. Leave their registries, storage, presentation and retrieval unchanged. Search and timelines can aid adjudication when exact vintage provenance is independently verified. |

## Panel and target

Freeze one protocol per estimand before the first relevant decision. Register the unit roster and boundary
version (for example ISO country plus a dated geographic crosswalk), UTC origin cadence,
eligibility, target ID/version, event and actor filters, severity criterion, outcome maturity
lag, and exact half-open observation windows. An example target is first qualifying onset
in a country over the next 30 days, with a prespecified event taxonomy and prior quiet
period. Escalation or continuing violence requires a separate target. For dyads or admin1
units, define attribution, disputed areas and boundary changes in advance. Never silently
roll admin1 forecasts into country scores.

For each scheduled origin retain an expected slot regardless of whether a prediction was
issued. Specify lead (origin to window start) and duration separately. An immediate
30-day target can use `[origin, origin + 30 days)` once the handoff instant is defined.
PR #34 accepts only studies whose registered window starts strictly after the cutoff.
Use a compatible evaluator for a registered zero-lead study.
Specify whether timestamps represent exact instants or date-only bounds. When a timestamp
has only day precision, require its latest plausible instant to precede or equal the
cutoff. Retain issuance, availability, retrieval and target dates separately.

Resolve outcomes using a frozen, versioned observation vintage and separate adjudication
rules. A zero requires affirmative surveillance coverage and a fully adjudicated window.
Missing predictions, uncertain labels, immature outcomes, ambiguous boundaries and incomplete
coverage are explicit exclusions. Publish counts and denominators by time, geography and
source, including coverage before restricting to matched rows. Publish the inclusion rule
and a sensitivity analysis for selective coverage. Unquantified forecasts count as missing
for point-probability metrics.

## Evidence modes

| Mode | Requirements and interpretation |
| --- | --- |
| Synthetic | Invented inputs for code verification, labeled demonstration throughout. |
| Retrospective reconstruction | Later information, corrected snapshots or hindsight-informed design may be used for descriptive exploration. Record each such choice. |
| Historical out-of-sample replay | Refit and calibrate under rolling origins using verified historical vintages and untouched outer test outcomes. Log when the replay actually ran and preserve artifacts. The design and model class may postdate the events, which limits inference. Regenerated predictions have no original issuance claim. |
| Historical out-of-sample archive | An immutable original prediction with verified issue and availability by origin, a known training/calibration history, and frozen resolution rules for the evaluation. Use later outcomes solely to score it. |
| Prospective real time | Preregister the protocol before the first decision, log immutable predictions and abstentions in real time, and score after maturity. Show issuance delays, drift and coverage through the evaluation period. |

Treat replays tuned against the outer test outcomes as retrospective. Never promote
a synthetic fixture or reconstruction by relabeling its outputs. Preserve source and
mode through export, scoring, reporting and any visualization. Numeric scoring requires
an exact verified binary probability. CAST expected counts, native VIEWS values with
unspecified semantics, and interval midpoints do not qualify.

## Point-in-time controls

- Pin release/version and content hash for every feature, training label, learned
  transform, pretrained artifact, calibrator and forecast. Record independent evidence
  for the exact vintage's first availability. Use release logs, signed archival exports,
  original publication metadata or equivalent timestamped evidence. A retrieval timestamp
  can bound availability if it certifies those exact bytes were seen by the cutoff.
- Select the latest eligible revision at each origin. Preserve superseded versions.
  Reject point-in-time eligibility when the vintage or availability cannot be established.
  Later corrections may resolve test outcomes after a fixed maturity lag. They cannot
  feed historical training unless they were available by the corresponding fit.
- Use forward-chaining with train before calibration before test. Within each partition,
  select features by the example origin and labels by model fit or calibration time.
  Keep preprocessing, feature selection, hyperparameters, alert thresholds and model
  selection inside development folds. Reserve the outer test panel until choices are fixed.
- Purge development examples whose outcome windows cross the next partition's first
  origin. Require a preregistered nonnegative embargo between each development outcome
  end and the next partition. Choose the gap based on data latency, feature reuse and
  dependence. Equality is allowed at a half-open boundary with zero embargo. Use a
  positive gap when same-instant availability cannot be established.
- Use one fold manifest per model or baseline and decision cutoff. Include exact
  manifests for feature dependencies and training examples. The code checks ordering
  and boundaries, while independent review must verify archive authenticity, manifest
  completeness, coverage, transformations and absence of test-driven model selection.
  For a replay, fit/calibration timestamps represent simulated information freezes.
  Retain simulated forecast issue and availability in the replay clock, with the actual
  computation and publication times in the immutable run manifest.
  A fixed external artifact still needs its availability and training lineage reviewed.
- Outcome overlap within a test panel inflates effective sample size. Preserve cases
  for coverage reporting and account for dependence when estimating uncertainty.
  Do not treat repeated alerts or repeated origins before one incident as independent
  events. If a credible uncertainty design is infeasible, report that limitation.

## Scores and uncertainty

Apply each metric within one target, geography definition, horizon and panel design.
Publish positives, negatives, exposure, exclusions and the exact scoring population.

| Metric | Definition and eligibility |
| --- | --- |
| Brier | Mean squared error between probability and binary outcome, including endpoint forecasts. Valid on any nonempty eligible sample. Optionally report skill relative to the matched baseline, undefined when baseline Brier is zero. |
| Log loss | Mean negative natural logarithm of probability assigned to the realized outcome. A confident contradiction has infinite theoretical loss. If flooring that probability (as in #34), report the floor and number of affected cases. |
| Reliability curve and ECE | Predetermine bins. Show bin count, mean probability and event frequency. ECE is the sample-weighted absolute gap across populated bins. Empty bins carry zero weight and an undefined observed rate. Sparse bins and bin choice can hide miscalibration. |
| Precision, recall, false alarm rate | With a threshold fixed in development, use TP/(TP+FP), TP/(TP+FN) and FP/(FP+TN). Null on a zero denominator. For warning operations also report false alert episodes per observed unit-time and alert duration. |
| PR-AUC | Predeclare average precision (step-weighted precision by recall increments) and group ties. Report prevalence as a reference. Suppress discrimination estimates if either class is absent. |
| ROC-AUC | Pairwise positive-over-negative ranking probability with half credit for ties. Requires both classes. Even high ROC-AUC can coexist with low operational precision for rare events. |
| Lead time | Time from the first eligible alert episode in a fixed pre-onset lookback to observed onset. Use actual availability, censor gaps, and match episodes to at most one onset using a preregistered rule. Report misses and the detection fraction beside the conditional lead-time distribution. Post-onset flags are late detections if tracked separately. |
| Coverage | Forecasts satisfying time and target rules divided by expected slots. Also report outcome coverage, joint scoring coverage and per-baseline intersection coverage. An empty denominator yields null. |

Use `geointel.historical_validation.discrimination.discrimination` for average
precision and ROC-AUC on already-matched binary rows. It groups tied probabilities,
returns sample class counts and marks empty or single-class samples as undefined.
The caller verifies target, horizon, window, coverage and archive semantics before
constructing the input rows. For comparisons, `paired_discrimination` takes a
single stream of exact matches so both sides use the same outcomes.

Record nulls with reason codes and show denominators. Retain natural prevalence.
If sampling controls, register weighting and correct prevalence-sensitive estimates;
do not apply balanced test resampling as if it represented field performance. Compare
models using paired differences on identical slots. Prefer a prespecified temporal
block bootstrap resampling whole cross-sections to retain common shocks and horizon
overlap. Select block length in advance with a sensitivity check; use incident or
geography clustering when defensible under the dependence structure. Record seed,
resamples, interval level, and fraction of class-degenerate resamples. With too few
effective blocks or incidents, report uncertainty as unavailable and give counts.
No pooled headline score across incompatible windows or targets.

## Baseline protocol

Freeze versions and parameters under the same fold audit. Emit candidate baseline rows
under the same target, horizon, geography and exact window keys as the evaluated model.
Use the reviewed #34 archive interface once available, and evaluate pairs on the exact
matched intersection. Retain the digest of sorted exact keys and the coverage of each
side before intersection. Hash the canonical JSON key list using UTF-8, stable UTC
timestamp serialization and a documented key order.

- Historical frequency uses matured, covered training slots with the same target
  definition and schedule. Predeclare training interval and smoothing (for example a
  fixed beta prior), and abstain if required coverage is absent.
- Persistence predicts continuation of the last comparable eligible state. For a
  probabilistic onset target, estimate conditional transitions on development data
  and declare the missing-state rule. For no-change alert comparisons, preserve the
  last eligible advisory under a prespecified freshness limit.
- Region-specific rates use a versioned region mapping and eligible training slots.
  Define minimum support and any pooled shrinkage or fallback ahead of time.
- Reference forecasts require verified archival availability and identical meaning.
  Expected counts cannot be converted to event probabilities from their means alone.

## Integration order

1. Review the protocol, target mapping and versioned archives. Resolve governance
   separately. Use #24 for approved taxonomy where applicable and #33 for diagnostic
   coverage where supported by its contract.
2. Review #34 and connect its evaluator through an offline adapter. Implement baseline
   fitting and supplemental diagnostics against that interface. Verify matched keys,
   hashes and outcome labels before attaching any scoring artifacts.
3. Choose the advisory contract from #35/#37 before adding episode matching, historical
   threshold validation and forward replay. Run the adjudicated full panel before
   drawing skill conclusions, then preregister and collect prospective forecasts.

See [historical cases](HISTORICAL_VALIDATION_CASES.md) and the
[report template](HISTORICAL_BENCHMARK_REPORT.md).
