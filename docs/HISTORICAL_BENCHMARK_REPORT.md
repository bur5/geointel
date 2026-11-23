# Benchmark report template

Use one report per evidence mode, exact target, geography definition and horizon.
Preserve the metadata alongside the scoring artifact.

| Field | Fill in before publication |
| --- | --- |
| Evidence mode and status | Synthetic demonstration, descriptive reconstruction, historical replay, original historical archive, or prospective. Include provenance review status and unresolved issues. |
| Model and comparators | Name, version, immutable archive, fitting/calibration protocol, baseline parameter versions and archive IDs. |
| Dataset and execution | Dataset version, immutable panel and outcome snapshots, code revision, command, dependency versions, configuration and seed. |
| Evaluation contract | UTC origin period, cadence, geography roster/crosswalk, target and operational definition, lead, window duration and interval convention, adjudication freeze and maturity lag. |
| Coverage and exclusions | Expected slots, valid forecasts and resolved outcomes separately, matched scored rows, events and prevalence (events/scored), exclusions by disjoint reason, coverage by time and geography, selection sensitivity. |
| Matched comparisons | Canonical digest of exact matched keys, linked score artifact with each model's absolute metrics and paired differences, threshold and rationale, null reasons and denominator counts. |
| Calibration | Linked bin table/curve, bin rule, ECE and support, log-loss floor and affected rows, any outcome or prevalence shift. |
| Uncertainty | Confidence level, estimation procedure, independent blocks or episodes, effective support, interval on each paired difference, or reason interval unavailable. |
| Warnings | Episode and incident definitions, exposure, false alert burden, detection fraction, lead-time distribution and censoring. |
| Leakage audit | Fold manifests, independent availability evidence, version/revision handling, fit/calibration boundaries, embargo, unresolved provenance issues and reviewer decision. |
| Known limitations | Coverage gaps, dependence, rare-event instability, outcome disputes, scope restrictions and external validity. |

## Machine-readable manifest

Validate inputs with `ReportRequest` and pass an independently verified
`Registration` receipt to `build_report` to produce a schema-version 2 manifest.
The receipt must come from an immutable registry or independently verified
timestamp evidence and must identify the exact registered plan digest, availability
instant and evidence reference. Do not derive a trusted receipt from a fold or
generate one from the plan at report time. The library has no registry client.

The registered plan fixes the target version, horizon, geography and panel, and
sets exact elapsed forecast lead, window duration, outcome maturity and embargo.
Use UTC-equivalent durations (one day is 24 hours). Every fold supplies the same
receipt, whose availability must strictly precede the earliest fold or development
decision, including simulated origins in a historical replay. Development labels
must be available at or after maturity and by fit or calibration. The evaluation
outcome freeze must be at or after test-window maturity. A separate `outcomes`
block identifies the one realized outcome vintage, which may be published after
registration. References in historical manifests still require source verification.

The request hash covers the normalized request, including the one outcome vintage,
and preserves list order. Any fold finding blocks the report. Both the request and
report schemas require an empty `comparisons` array until a verified adapter exists.
Clean historical and prospective manifests retain `provenance_review_required`.
Freeze the original input and the independent receipt for reproduction.

The following example uses the two synthetic fixtures and produces a demonstration
manifest with no empirical scores.

```sh
python - <<'PYCODE'
from pathlib import Path

from geointel.historical_validation.audit import Registration
from geointel.historical_validation.report import ReportRequest, build_report

fixtures = Path("tests/fixtures")
request = ReportRequest.model_validate_json(
    (fixtures / "synthetic_benchmark_request.json").read_bytes()
)
receipt = Registration.model_validate_json(
    (fixtures / "synthetic_benchmark_registration.json").read_bytes()
)
print(build_report(request, verified_registration=receipt).model_dump_json(indent=2))
PYCODE
```

## PR #34 adapter requirements

PR #34 (`ea585b341233c636874dcbb932a22d4d5fe89f39`) accepts a `Study` with a
`Contract`, explicit panel `Case` rows, `ModelArchive` prediction rows, and
one `outcome_snapshot` with observation rows. Predictions match by contract,
location, origin and both target-window endpoints. Observations match by contract,
location and both window endpoints. Its `evaluate` function emits status and
record IDs, per-model metrics and scores over the intersection of eligible
panel indices. Report indices are positions in that specific panel. The adapter
must work from the immutable input records and joined values.

1. Resolve the registered panel, audited folds and forecast artifacts, baseline
   construction/availability manifests, and the reviewed outcome vintage.
   Normalize all temporal values to UTC before matching or passing inputs to #34.
   Define case identity using versioned target, geography and horizon, location,
   origin and both window endpoints. Carry the fold key and verified prediction and
   observation record IDs and snapshot references through the join. Reject duplicate
   canonical cases or fold keys, ambiguous matches and cross-vintage outcomes.
2. Verify target identity, geography, window convention and estimand. #34 uses
   integer calendar-month horizons, distinguishes probabilities from expected
   counts, and requires `origin < start < end`. Match the exact registered endpoint
   semantics. A zero-lead case or an incompatible horizon needs a supported
   evaluator. Shifting timestamps or coercing counts into probabilities changes
   the evaluation contract.
3. Retain actual publication, input-cutoff and availability timestamps in provenance
   and retain simulated fit, calibration, issue and availability clocks separately.
   Check each clock against its own role and keep the original evidence mode. #34's
   pre-origin gate can operate directly on original archive or prospective records
   only when those records meet its conditions. A replay pathway needs an explicit
   simulated-clock contract with independently verified historical input vintages.
   #34's two-valued `data_kind` cannot carry the evidence mode by itself.
4. Require complete, mature outcomes available by the registered freeze for the
   reviewed vintage, and require both model and baseline to qualify independently
   on the same eligible canonical cases. Reject duplicate or disjoint samples and
   population mismatches even if #34 can score their intersection. Retain all
   panel exclusions and their reasons. A numerically valid #34 result with an
   incompatible origin, window, maturity, evidence mode or eligible population
   is ineligible for attachment.
5. Derive denominators, event and exclusion counts, metrics, calibration and
   paired uncertainty from the validated joined rows, with uncertainty methods
   registered in advance. Compute the comparison digest from canonically ordered
   rows including fold and case identities, values and immutable references.
   Verify that any emitted scores use the identical audited population. The
   paired AP and ROC-AUC utilities apply to binary rows after that join.

The adapter and independent registry/archival verification remain integration
work. The manifest provides no empirical performance estimates.
