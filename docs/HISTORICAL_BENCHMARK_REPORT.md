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

Use `geointel.historical_validation.report.ReportRequest` to validate inputs and
`build_report` to generate a deterministic `BenchmarkReport`. Snapshot references
must resolve to immutable artifacts. Comparisons reference a reviewed scoring
artifact and the digest of its matched keys. The generator has no scorer or access
to external artifacts. The future #34 adapter must verify that score artifacts,
matched keys, fold manifests, model and baseline snapshots all describe the same
study before reporting. Any fold finding blocks score attachments. Clean historical
and prospective manifests retain `provenance_review_required`. Preserve this label,
and document any independent verification separately. The request hash covers
serialized request contents, including folds and comparisons, and retains list
order. Freeze the exact input file for replay.

```sh
python -c 'import json; from geointel.historical_validation.report import BenchmarkReport; print(json.dumps(BenchmarkReport.model_json_schema(), indent=2))'
python -c 'from pathlib import Path; from geointel.historical_validation.report import ReportRequest, build_report; print(build_report(ReportRequest.model_validate_json(Path("request.json").read_bytes())).model_dump_json(indent=2))'
```

A synthetic request fixture is shipped in
[tests/fixtures/synthetic_benchmark_request.json](../tests/fixtures/synthetic_benchmark_request.json).
It is a demonstration of audit and report generation and contains no measured results.
