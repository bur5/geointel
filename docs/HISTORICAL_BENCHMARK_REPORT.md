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
`Registration` receipt to `build_report` to produce a schema-version 4 manifest.
The receipt must come from an immutable registry or independently verified
timestamp evidence and must identify the exact registered plan digest, availability
instant, evidence reference and registered evidence mode. Every fold must use that
mode. Do not derive a trusted receipt from a fold or
generate one from the plan at report time. The library has no registry client.

The registered plan fixes the target version, horizon and geography, and
sets exact elapsed forecast lead, window duration, outcome maturity and embargo.
Use UTC-equivalent durations (one day is 24 hours). Every fold supplies the same
receipt, whose availability must strictly precede the earliest fold origin, forecast
issuance used for the decision, fit, calibration, or development origin. For a replay
the audit uses the simulated decision clocks and requires actual publication to
follow or coincide with simulated forecast availability. Development labels
must be available at or after maturity and by fit or calibration. The evaluation
outcome freeze must be at or after test-window maturity. Development cases are
unique within a fold by geography, UTC origin and window endpoints, regardless
of row key or split role. An omitted development geography inherits the fold's
geography. Within a report, each immutable snapshot ID has one set of
availability metadata across all folds, development features and labels, evaluation
features, forecasts, the receipt and the outcome publication. Comparisons use UTC
instants and include dataset version and actual forecast issue time where declared.
An omitted version in a legacy record leaves that metadata unspecified. Known
versions must agree with each other and with the outcome version wherever the
same snapshot is used. Use separate immutable references for distinct vintages.
A single dataset snapshot may serve multiple cases and geographies. Case origins,
windows and simulated replay clocks describe the cases or replay runs.

Before registration, use `EvaluationPanel.digest()` to bind the panel snapshot
and its complete slot roster in the plan's `panel_sha256`. A slot includes the
geography, origin and both window endpoints, plus a reason if the slot is excluded.
The digest uses UTC instants and canonical slot order. Supply the artifact as
`resolved_panel`. Duplicate slots, unregistered folds and folds occupying excluded
slots are rejected. Registered exclusions remain visible in the resolved panel,
and any missing required slot is listed and blocks the report. When the panel
cannot be resolved, or the plan carries only a snapshot reference, panel integrity
remains unverified and missing/excluded totals cannot be inferred from submitted folds.

The `outcomes` block identifies the realized vintage, which may be selected and
published after registration. Pass `verified_outcome_publication` only after
independently confirming the availability timestamp and evidence reference for
that exact dataset version and snapshot. Availability at the freeze passes,
and later availability is rejected. Publication verification establishes
availability of the exact outcome vintage. Per-case outcome completeness
and accuracy require separate checks.

The request hash covers the normalized request, including the one outcome vintage,
and preserves list order. Any fold finding blocks the report. Both the request and
report schemas require an empty `comparisons` array until a verified adapter exists.
Clean historical and prospective manifests retain `provenance_review_required`.
Freeze the original request, independent receipt, panel roster, publication, and
source records for reproduction. Existing plan, panel and request digests retain
their semantics. A declared dataset version participates in the request digest.

The following example uses the synthetic fixtures and produces a demonstration
manifest with no empirical scores.

```sh
python - <<'PYCODE'
from pathlib import Path

from geointel.historical_validation.audit import Registration
from geointel.historical_validation.report import EvaluationPanel, ReportRequest, build_report

fixtures = Path("tests/fixtures")
request = ReportRequest.model_validate_json(
    (fixtures / "synthetic_benchmark_request.json").read_bytes()
)
receipt = Registration.model_validate_json(
    (fixtures / "synthetic_benchmark_registration.json").read_bytes()
)
panel = EvaluationPanel.model_validate_json(
    (fixtures / "synthetic_benchmark_panel.json").read_bytes()
)
print(build_report(request, verified_registration=receipt, resolved_panel=panel).model_dump_json(indent=2))
PYCODE
```

## Verifying a saved manifest

`BenchmarkReport.model_validate` and `model_validate_json` parse structural
manifests. Schema version 4 records `unverified` for panel and publication checks,
or `incomplete` where the embedded roster accounts for missing required slots.
Schema-version 3 files still parse, with embedded verification claims downgraded.
`build_report` retains its signature and returns a structural manifest. Callers
that used its `verified` statuses should migrate to `verify_report_v1`.

Pass the parsed report and the independently preserved `original_request`,
authenticated `registration`, registered `required_panel`, trusted
`evidence_mode`, authenticated `outcome_publication`, and `source_snapshots`
to `verify_report_v1`. Supply source snapshots as `SnapshotEvidence` records
resolved independently, including the exact snapshot ID, availability time and
evidence reference, dataset version where declared, and actual issue time for
forecast snapshots. Use `ReportRequest.snapshot_declarations()` to enumerate
which references and fields need resolution. The verifier recomputes all audits
and panel accounting, checks publication and source metadata, and compares the
rebuilt manifest with the supplied one. It relies on the caller to authenticate
the independent records and their source identities.

Verification returns a frozen `VerifiedReport` whose digest covers the normalized
manifest content. Keep this result in the trusted caller. For a saved manifest,
rerun verification from independent evidence. Use `result.matches(report)` before reusing a prior result with
a manifest. Changes to the normalized content require re-verification. A verified result can still report an incomplete panel or coexist
with blocked audit findings. Provenance review remains required for clean
historical or prospective manifests. Synthetic examples are illustrative.
Empirical performance claims require independently authenticated forecast
and outcome archives, plus an eligible scoring analysis.

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
