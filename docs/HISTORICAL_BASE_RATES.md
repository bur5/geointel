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
  latest_observed_date, coverage_end, reference_date, reference_basis, historical,
  coverage_semantics, observation_count.
- `observation_statistics`: observation_count, dated_observation_count,
  earliest_observation_date, latest_observation_date, earliest_year, latest_year,
  observed_year_span (inclusive), distinct_observed_year_count,
  years_since_latest_observation (calendar year difference from analysis date).
- `fatality_statistics`: best_total, low_total, high_total, best_available_count,
  low_available_count, high_available_count, median_best_per_observation,
  maximum_best_per_observation. Totals sum available values, not imputed values.
- `trailing_window_counts`: coverage index to 5y/10y/20y observation counts.
- `category_statistics`: explicitly present normalized category field to value
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
