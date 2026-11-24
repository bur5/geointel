# Historical forecast evaluation

Backtesting v1 scores frozen local exports. It has no provider, database, or scheduler entry
point. This repository has synthetic inputs for testing and no bundled historical archive
with forecast vintages and complete, matched outcomes.

| Interface on main | Available fields and retrospective use |
| --- | --- |
| [VIEWS adapter](../src/geointel/connectors/views.py) | Operator-supplied forecasts with issue time, exact target dates, optional horizon, geographic fields, target, value, and optional unit and scale. The adapter does not guarantee access to past vintages or probability semantics. Use only a verified binary probability export for binary scoring. |
| [ACLED CAST](../src/geointel/connectors/cast.py) | Official rows contain monthly country or admin1 expected counts for total events, battles, explosions/remote violence, and violence against civilians. The adapter retains rows for elapsed target months, maps the provider timestamp to issue date, and leaves the forecast horizon and model version unspecified. An elapsed target month does not establish that its value was available before the forecast origin. A country-filtered response does not establish vintage coverage. |
| [ACLED Event](../src/geointel/connectors/acled.py) | Individual observed event reports carry occurrence date, location, event type, provider ID, and optional update timestamp. The official connector queries a bounded recent window. Its responses do not establish historical completeness or justify zero events in an empty window. |
| [ForecastSignal and NormalizedForecastSignal](../src/geointel/domain/models.py) | Persisted run-linked signals preserve native value, unit, scale, issue and target dates, origin geography, retrieval time, and provenance. They do not independently certify first availability, model input cutoff, archival completeness, or observed outcomes. Retrieval can happen after issuance and after the target window. |

GEOINTEL's own assessments may be qualitative or express probability intervals. The evaluator
accepts documented point probabilities of a binary event and expected event counts. Probability
intervals, qualitative judgments, arbitrary risk scores, and fatality counts have no v1 scoring
contract. A CAST expected count cannot be converted to a binary probability from its mean alone.

## Run locally

```sh
python -m geointel.backtesting study.json > report.json
```

The same interface is available as `geointel.backtesting.evaluate(study)`. To inspect the
input JSON schema, run the following from an installed checkout.

```sh
python -c 'import json; from geointel.backtesting import Study; print(json.dumps(Study.model_json_schema(), indent=2))'
```

1. Freeze a **panel** before inspecting results. Set `panel_snapshot` to an immutable
   reference and include every requested forecast opportunity, even where a forecast or
   outcome is absent. Set `data_kind` to `synthetic` or `historical` and pin `as_of`.
2. Use one **contract** per study. Its versioned `target` identifies an exact event
   definition, filters, counting/aggregation rules, and horizon convention. Use a positive
   provider-verified `horizon_months` and a versioned geography definition if boundaries
   can change. Lead time is a provider convention and window length is separate. Verify
   each row's declared horizon against its origin and target dates during export. The
   evaluator checks equality of declared horizons and exact windows.
3. Each **case** has a canonical `location`, UTC `origin` (the forecast decision cutoff),
   and a half-open UTC window `[start, end)` strictly after that origin. Use
   country-qualified admin1 identifiers. Resolve geographic aliases and provider date
   conventions before export. For CAST, use the first instant of the following month
   as the exclusive end. The evaluator matches exact keys without geographic fallback.
4. Each **model archive** supplies its model, version and immutable `snapshot` reference.
   Each prediction includes its case, native contract mapping, record ID, value,
   `issued_at`, `available_at` (first availability of that exact vintage), and
   `input_cutoff` (latest availability of inputs used, including model fitting and
   calibration). Require independently supported timestamps.
   The evaluator requires input cutoff ≤ issue ≤ availability ≤ origin. Never substitute
   retrieval time, a nominal model-run date, or the timestamp of a different vintage.
   A later retrospective reconstruction that was unavailable at the origin is ineligible.
5. Each **observation** supplies the same contract, exact geography and target window,
   record ID, coverage flag, integer outcome and availability time. Pin `outcome_snapshot`.
   Derive outcomes offline by deduplicating and applying the precise target definition to
   an audited observation vintage. A zero is eligible only when explicitly provided in a
   window marked complete. Null values, missing rows, incomplete windows, and observations
   available after `as_of` are excluded with their own status. Availability must be at or
   after the exclusive window end. Choose one outcome vintage per key under a documented
   revision and maturity policy before export.
6. Optionally give a binary classification `threshold` with its numeric `value` and
   nonempty `rationale`. Fix the threshold in advance or using only earlier training data.

All timestamp strings require a UTC offset. Unknown JSON fields, duplicate case or observation
keys, duplicate forecasts within a model/case, and mixed contracts fail validation. Outside-panel
records are counted separately. Use immutable snapshot IDs or hashes and retain the input JSON
with the report so the exact run can be reproduced.

## Interpret the report

The versioned JSON contains the run methodology, source snapshot references, per-case and
per-model record IDs and eligibility, and the scores. Coverage denominators include every
expected panel case. Probability metrics include mean Brier and natural-log loss, flooring the
probability assigned to the realized class at `1e-15` for log loss. Calibration bins show
sample count, mean prediction and observed frequency in ten equal-width intervals, with the
final bin including one. Classification predicts positive at or above the supplied threshold.
Undefined ratios and empty scores are JSON null. Counts use mean absolute error. The descriptive
small-sample flag identifies 1–29 scored cases and does not establish statistical significance.

Per-model scores can use different available cases. Use the `comparison` section for direct
comparisons. It rescores every model on the exact intersection under the same target, horizon,
geographic unit, and outcomes. Coverage and the shared case indices reveal what was excluded.
Missingness can be systematic and overlapping horizons can introduce dependence.

## Real historical evaluation and rolling origins

Acquire authorized, immutable offline forecast vintages with independent availability and input
cutoff evidence. Verify target definitions, CAST lead times and model versions, VIEWS units, and
aligned observation vintages with coverage evidence. Audit positive and explicit zero windows
against those sources before evaluating. Report coverage by origin and geography, along with the
effects of data revisions and exclusions.

For rolling-origin evaluation, predeclare a sequence of origins, training windows, test windows,
geographic units, horizons, and a consistent outcome maturity lag. At each origin, fit or
calibrate using only records and labels available by that cutoff, freeze the forecast vintage,
and evaluate the later window with an independently frozen outcome snapshot. Reuse the panel
contract and shared sample for comparisons including baselines. Report results per origin and
pooled under a documented weighting rule, and account for spatial dependence and overlapping
target windows when estimating uncertainty.

Synthetic tests establish scoring and eligibility behavior. Historical model performance remains
unevaluated.
