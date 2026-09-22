# Five-country validation framework

## Purpose and neutrality

Validation evaluates GEOINTEL's behavior—not whether it reaches a preferred geopolitical conclusion. `five-country-v1` contains Spain, Georgia, Taiwan, Serbia, and Nigeria as heterogeneous analytical test conditions. **The order is not a risk ranking**, no case has an expected risk label, and the framework produces neither a country score nor political recommendation.

The neutral validation roles are: Spain tests sparse/control false positives; Georgia tests structural exposure versus imminent escalation and stale context; Taiwan tests interstate isolation, high-attention strategic language, conflicting signals, and uncertainty; Serbia tests historical determinism and theory bias amid sparse operational material; Nigeria tests event density, subnational variation, aggregation, duplicate identity, fatality uncertainty, and distinctions among violence categories. These are test roles, not current-world verdicts.

## Suite and synthetic fixture policy

The packaged, reviewable `five-country-v1.json` declares exactly five stable case IDs, ISO-style geography identifiers, purpose, scenario, source conditions, and suite/version metadata. The common question asks about 12 months and exactly the four established conflict categories. Every fixture and every generated record is explicitly marked synthetic. Fixture prose is not intelligence and makes no actual claim about any named country.

Fixtures are bounded data. The loader accepts only the named packaged suite, caps it at 100 KB, uses a strict schema, rejects extra fields, and performs no URL access, path selection, dynamic import, template evaluation, or code execution. Fixed timestamps and exact provider IDs make runs reproducible. Offline fixture connectors represent available, missing, failed, stale, and mismatched inputs; `OfflineModel` prevents external LLM access. Validation never instantiates live UCDP, ACLED, VIEWS, or CAST connectors.

## Domain, pipeline, and persistence

`ValidationSuite` and `ValidationCase` describe evaluation inputs. `ValidationRunner` injects fixture connectors and `OfflineModel` into the normal `AnalysisPipeline`; it does not implement a second forecasting engine. The pipeline therefore persists a normal `AnalysisRun`, four immutable forecasts, empirical records, predictive signals, mandatory Red Team output, synthesis, and separate strategic interpretation.

Migration 0006 adds `validation_suites`, `validation_runs`, and `validation_results`. A suite row stores identity, version, and a definition digest rather than fixture content. Each validation run links to exactly one analysis run, identifies its case, preserves a five-source matrix, implementation version, status, and timestamps. Every assertion is an individual result with status, explanation, related object IDs, and implementation version. Repeated execution is append-only history.

## Assertions and failure semantics

The explicit assertion taxonomy covers exact categories; forecast immutability; provenance; source and strategic separation; missing-source and disagreement disclosure; no fabricated probability; isolated-event restraint; no theory override; temporal/geographic mismatch disclosure; mandatory and bias-aware Red Team review; uncertainty; non-fatal optional failures; repeated history; offline reproducibility; no cross-source fuzzy dedupe; and the sparse-control false-positive guard.

- **PASS** means the evaluated behavioral invariant held.
- **FAIL** means analysis completed but violated that invariant.
- **ERROR** is reserved for validation infrastructure/evaluation failure, not an analytical disagreement.
- **N/A** is available for an assertion whose precondition does not apply.

There is no combined validation score. Output retains each result and only counts pass/fail/error/N/A totals.

## Source matrix and metamorphic coverage

Every run shows UCDP, ACLED, VIEWS, CAST, and Strategic Knowledge as available, missing, failed, stale, or mismatched. Missing is disclosed as unavailable—not converted into safety or zero risk.

Metamorphic checks compare controlled fixture changes: an isolated event cannot populate escalation evidence across categories; removing CAST produces missing-source disclosure; opposed VIEWS/CAST native values produce disagreement rather than an ensemble; strong strategic framing remains interpretation and cannot create a probability; an exact ACLED provider duplicate is removed; similar records with distinct provider identity remain distinct; stale material remains marked; and subnational/country mismatch produces alignment warnings. High-volume input is deterministically bounded and retains uncertain fatalities.

## CLI

Run the complete suite or one stable case:

```bash
python -m geointel.validation run five-country-v1
python -m geointel.validation run five-country-v1 --case spain
python -m geointel.validation run five-country-v1 --json
```

The CLI uses the configured database, creates absent development tables for convenience, writes auditable records, and performs no network access. JSON output has suite metadata, per-case run IDs/source matrix/results, and count summary. Human output lists assertions by country but never compares country risk.

## Adding future suites

Add a bounded static data file, a strict allowlisted loader entry, stable case IDs, synthetic labels, neutral validation roles, and behavioral assertions. Add fixture generation only for analytical conditions—not claims about actual places—and regression tests for loader limits, offline execution, epistemic boundaries, persistence, CLI output, and migration compatibility. Increment suite version whenever its definition changes.

## Limitations

This release is property testing with synthetic inputs, not calibration, historical backtesting, current intelligence, source-quality adjudication, or evidence that real-world forecasts are accurate. The deterministic model is intentionally unquantified. Assertion implementation itself requires review, and a passing suite cannot establish completeness, absence of bias, or production readiness.

## Monitoring validation (v0.1.0)

Sequential monitoring properties live in a separate deterministic test suite rather than changing
`five-country-v1`: they require baseline-to-transition comparisons and persisted alert lifecycle
state, whereas five-country validation remains a one-run behavioral suite. The monitoring suite
covers no-baseline/identical/duplicate alert behavior, strategic-only and outage restraint,
provenance/counterevidence, deduplication, resolution, and repeated synthetic Spain control runs.
Both suites use the normal pipeline and `OfflineModel` without network access.
