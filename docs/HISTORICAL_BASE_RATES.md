# Historical observation feature contract

Annual GED is historical, including GED 26.1. A recent retrieval timestamp does
not make its observations current. Classification uses explicit `temporal_role`,
not a provider name. Only `annual_historical` and `historical` enter the feature
component; only `current_operational` and `recent_operational` enter current
structured evidence. Candidate GED remains separate candidate coverage.

The typed `HistoricalBaseRateSummary` is persisted in AnalysisRun's existing JSON
collection metadata and analyst output, both exposed by the API. No migration is
required. Raw normalized observations and original provenance remain in Evidence.

Schema (nullable values remain null when unavailable):

- `status`: available or unavailable; `method_version`: historical-observations-v1;
  `geography`: requested geography.
- `coverage[]`: provider, dataset, resource, dataset_version, temporal_role,
  requested_geography, resolved_provider_geography_id, earliest_observed_date,
  latest_observed_date, coverage_start, coverage_end, reference_date, reference_basis, historical,
  coverage_semantics, observation_count.
- `observation_statistics`: observation_count, dated_observation_count,
  earliest_observation_date, latest_observation_date, earliest_year, latest_year,
  observed_year_span (inclusive), distinct_observed_year_count,
  years_since_latest_observation (calendar year difference from analysis date).
- `fatality_statistics`: best_total, low_total, high_total, best_available_count,
  low_available_count, high_available_count, median_best_per_observation,
  maximum_best_per_observation. Totals sum available values, not imputed values.
- `trailing_window_counts`: coverage index to 5y/10y/20y observation counts.
- `category_statistics`: explicitly present provider category field to value
  counts; `category_available_counts`: field completeness counts.
- `caveats`: censoring, missingness, sparse history and probability restraint.

Coverage dates are accepted only when explicit provider provenance supplies them.
Dataset version numbers do not establish a coverage end. Where unknown, the
latest observation anchors windows and is labeled as an observation reference,
not dataset coverage. Windows are (reference minus N calendar years, reference],
with February 29 clamped to February 28. Counts use observation start dates.
No events after the coverage end cannot establish no violence after that date;
observed-year span is not a population of fully observed years. Multiple datasets
retain separate coverage entries and window counts; observations are not claimed
to be independently corroborated across datasets.

The analyst presents compact historical context; current evidence stays separate.
Red-team checks flag historical input or repeated historical narrative in current
observations and warn against present-day coverage assumptions, fatality/event
confusion, sparse history and inferred categories. Synthesis acknowledges available
history separately from missing operational coverage. Numeric probabilities remain
unset without calibration. Future forecasting models must document target,
exposure/coverage, missingness, calibration and out-of-sample performance before
using these features to estimate probabilities.


## Normalized conflict taxonomy and reviewed GED mappings (v0.1.8)

The separate typed `NormalizedConflictType` enum contains exactly:

- `INTERSTATE_ARMED_CONFLICT`
- `INTERNAL_ARMED_CONFLICT`
- `INTERNATIONALIZED_INTERNAL_ARMED_CONFLICT`
- `ONE_SIDED_VIOLENCE`
- `MAJOR_POLITICAL_VIOLENCE`
- `OTHER_OR_UNRESOLVED`

The repository previously retained numeric GED categories but contained no authoritative
value definitions. These were verified against the official
[UCDP GED 26.1 codebook](https://ucdp.uu.se/downloads/ged/ged261.pdf), section 3.1 (page 6)
and section 5.2 (page 16), on 2026-10-06. The explicit deterministic mapping policy is
`provider-conflict-taxonomy-v1`:

| Provider/dataset/field | Original value and meaning | Normalized type | Mapping confidence |
| --- | --- | --- | --- |
| UCDP / GED / type_of_violence | 1: state-based conflict | OTHER_OR_UNRESOLVED | unresolved |
| UCDP / GED / type_of_violence | 2: non-state conflict | OTHER_OR_UNRESOLVED | unresolved |
| UCDP / GED / type_of_violence | 3: one-sided violence | ONE_SIDED_VIOLENCE | verified_direct |
| Missing/unknown value, unreviewed dataset/provider | original value retained | OTHER_OR_UNRESOLVED | unresolved |

State-based violence does not distinguish interstate/internal/internationalized internal
conflict. GED's non-state conflict category does not establish GEOINTEL internal armed conflict
or the scope/threshold of major political violence. No extra conflict metadata, episode counts,
political motive or country identity is inferred to bridge those gaps. Mapping confidence
expresses taxonomy review status, not event truth, current activity or forecast confidence.
The direct one-sided mapping retains UCDP's own inclusion criteria. Candidate remains separate,
delayed/non-real-time and excluded from historical profiles. Other providers await reviewed maps.

## HistoricalConflictProfile schema

Persisted in existing AnalysisRun JSON metadata and typed Analyst output; no new relational
migration is needed. API serialization exposes the same auditable structure. Raw Evidence
provenance is preserved. Method: `historical-conflict-profile-v1`.

- `status`, `geography`, `analysis_date`, `method_version`, `normalization_method_version`.
- `coverage[]`: the existing coverage structure plus explicit nullable `coverage_start`.
  Boundaries are accepted only from explicit provider provenance. Resolved geography falls back
  to the provider country ID when the reviewed resolution ID is unavailable.
- `overall`, `conflict_types[NormalizedConflictType]`: `HistoricalConflictFeatures`, with
  `observation_statistics` and `fatality_statistics` as documented above, `historical_presence`,
  `share_of_retrieved_historical_observations`, and `trailing_window_counts` keyed by the
  **overall profile's coverage index**. Every taxonomy member is present, including unresolved.
- `unresolved_observation_count`: included in overall and unresolved-group counts, not added
  twice. All per-type observation counts sum to the overall count.
- `normalization_audit[]`: provider, provider_dataset, provider_original_category,
  provider_original_value, provider_original_categories (all retained category fields),
  provider_category_meaning, normalized_conflict_type, mapping_confidence,
  mapping_method_version, mapping_notes, mapping_source, source_record_id, dataset_version,
  resource, requested_geography, observation_geography, resolved_provider_geography_id,
  temporal_role, coverage_index. Audits sort deterministically independent of input order.
- `annualized_rate_status`: `UNAVAILABLE_UNKNOWN_COVERAGE` when either boundary is missing;
  otherwise `UNAVAILABLE_UNVALIDATED_DENOMINATOR`. `annualized_observation_rate` is always null
  in this release and the typed schema rejects numeric values.
- `caveats`: explicit temporal, denominator, unit, completeness, unresolved and overlap limits.

Per-type windows share the same dataset references as overall windows, rather than silently
moving the reference to the most recent observation of each type. Window cutoffs are exclusive,
references inclusive; missing dates do not count. Multiple datasets retain independent reference
entries and may overlap: summed rows do not imply unique independently observed events.

`historical_presence` means at least one retrieved historical row in the group. A false value
means no retrieved rows, not proven historical absence. Shares divide by all retrieved historical
rows including unresolved mappings; empty denominators yield null. Fatality totals and median/max
use available nonnegative integer values only, accompanied by field-availability counts. Missing
fatalities are not imputed as zero. Years-since-latest is a calendar-year difference from the
explicit analysis date. Distinct observed years are not coverage duration. No trend, fatality
risk scale, episode count, per-year conflict frequency, percent of conflict years or probability
is produced. Optional future descriptors require separately reviewed definitions.

## Denominator and provenance safeguards

The codebook documents GED 26.1's global date range, but this does not establish the completeness
of a bounded/paginated retrieval or its geographic denominator. Accordingly version numbers do
not auto-fill coverage boundaries. Latest observations never become coverage ends; missing years
never become zero-conflict years. Even supplied start/end boundaries alone do not validate an
annualized denominator. Complete retrieval, exclusions, revisions and dataset dependence must be
reviewed before any future annualized feature is enabled.

Rows, years, episodes and fatalities are separate units: `observation_count != conflict_count`,
`distinct_observed_year_count != episode_count`, `fatality_total != event_frequency`. No episode
count is inferred from GED rows or IDs. Each feature group can be traced through its type and
coverage index to mapping audits and original provider/version/record provenance in Evidence.
No provider secrets or arbitrary provenance fields are copied into mapping audits.

Analyst/synthesis use compact normalized context; raw categories remain audit data. Mandatory
Red Team detects explicit positive misuse assertions with deterministic patterns and checks
structured audit completeness, forged mappings, unresolved loss, and unvalidated rates. Checks
are bounded and conservative, not a general-purpose semantic proof; arbitrary paraphrases may
require human review. Existing temporal leakage checks and numeric calibration safeguards remain.
Historical features never enter current coverage/evidence, operational events, escalation
indicators, or calibrated numeric probabilities. Future models must satisfy the forecasting
contract before treating these descriptive features as model inputs.

Monitoring retains historical context in persisted forecasts but excludes the exact audited
per-category descriptive context from material forecast-state comparisons. A change in historical
row counts alone cannot create an escalation alert; other unknowns, confidence, probabilities
and evidence remain compared normally.
