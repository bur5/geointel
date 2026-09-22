# Monitoring, change detection, and alerts (v0.1.0)

## Architecture and domain boundaries

Monitoring is a scheduler-ready orchestration layer over the **normal** `AnalysisPipeline`:
`Watchlist → WatchlistTarget → MonitoringRun → AnalysisRun → DetectedChange → Alert`. A watchlist
is a named collection; a target is currently a country identified by a stable operator-provided
geography ID. Future target types can be added, but region, city, border, route, and airport are not
implemented. Monitoring records are not Source, Evidence, Event, ForecastSignal, StrategicClaim,
StrategicAnalysis, or Forecast records. An alert is an auditable change decision, never a forecast,
event, evidence item, political recommendation, country ranking, or evacuation instruction.

Configuration strings and bounded JSON metadata are hostile **data**. They cannot select code,
tools, files, connectors, prompts, or execution privileges. Names/IDs are bounded, questions and
descriptions are capped, NULs are rejected, metadata is capped at 10 KB, and SQLAlchemy parameters
are used throughout.

## Cadence and execution

Supported UTC cadences are `hourly`, `every_6_hours`, `daily`, and `weekly`; sub-hour schedules are
rejected. A target is due only when its watchlist and target are enabled and `next_due_at <= now`.
After success, the next due time is the deterministic cadence interval after the invocation time.
There is intentionally no daemon, Celery, Redis, or APScheduler. An external scheduler may invoke:

```bash
python -m geointel.monitoring create-watchlist "Operations"
python -m geointel.monitoring add-target WATCHLIST_UUID ISO-ID "Display name" --cadence daily
python -m geointel.monitoring run-target TARGET_UUID
python -m geointel.monitoring run-due
python -m geointel.monitoring list-alerts
```

The CLI uses configured connectors (disabled by default) and `OfflineModel`, persists ordinary
analysis artifacts, prints JSON, and never executes target text. It does not deliver notifications.

## Runs, baselines, comparability, and failures

Every attempt starts a `MonitoringRun`. Success links the ordinary completed `AnalysisRun`, source
health, trigger, completion time, and prior comparable IDs. Failure is retained with a bounded
reason and no fabricated analysis link. Connector failure is different: the normal pipeline may
complete and disclose missing inputs, so the monitoring run succeeds.

The first successful run is a baseline and cannot alert. A prior run is comparable only when it is
for the same target, completed, has the same horizon, exact compatible pipeline version, and the
exact four-category forecast set. A horizon/version/taxonomy mismatch creates a new baseline.

## Structured changes and materiality

`ChangeDetector` ignores final prose and timestamps. It compares structured forecasts, unique
provider event identities, provider-native predictive signals, disagreement, source health,
confidence/uncertainty, strategic claim IDs, Red Team structure, and recency. Each persisted change
contains before/after state, category/source references, explanation, materiality/severity,
analysis-run provenance, and detection time.

Deterministic v0.1.0 materiality rules are conservative: structured forecast state or uncertainty
change is reviewable; at least two unique events from at least two represented sources are needed
for event materiality; predictive change needs multiple providers; multiple missing/failed sources
may create a **data-quality** alert; corroborated stale-to-current recency may be material. An
isolated event, duplicate provider ID, wording/order/timestamp change, one outage, strategic-only
change, or first baseline is not independently material. Numeric magnitude is never invented.

## Alert engine and lifecycle

The engine consumes persisted changes, current Red Team output, and source health. Alert fields
answer what changed, why it matters analytically, relevant evidence/provenance, counterevidence,
missing/disagreeing sources, affected categories, and what could confirm or reverse the condition.
Neutral `notable` priority is workflow metadata, not probability or calibrated risk.

Guardrails explicitly cover isolated/duplicate events, syndication uncertainty, missing/stale data,
geographic/horizon mismatch, predictions-as-fact, theory/analogy misuse, disagreement,
uncertainty, baseline safety, and false precision. Strategic literature alone cannot alert. A
source-health alert is labeled data quality rather than escalation. Red Team findings are retained
as counterevidence.

A SHA-256 key over canonical material structured changes and categories is unique per target.
Repeated observation updates `last_observed_at` instead of inserting another alert. Alerts have
`open` and `resolved` states; resolution sets a timestamp and never deletes history. v0.1.0 exposes
explicit resolution in the service domain; automated condition-clear inference is deliberately
conservative and remains future work.

## Source health, testing, and limitations

Each run reports UCDP, ACLED, VIEWS, CAST, and Strategic Knowledge independently as available,
missing, failed, stale, mismatched, or disabled where supplied by collection metadata. Availability
is not geopolitical risk and absence is not evidence of safety or escalation.

Offline tests inject synthetic connectors and `OfflineModel`; they cover baseline/identical runs,
Spain sparse-control behavior, isolated and duplicate events, corroboration, disagreement,
strategic-only change, outages, recency, deduplication, persistence, resolution, failure, UTC and
cadence behavior. Monitoring checks are separate from `five-country-v1` because monitoring tests
transitions between runs, while that suite evaluates one-run forecasting invariants. Neither suite
uses the network.

Known limitations include no production scheduler, delivery provider, authentication/authorization,
alert acknowledgement workflow, cross-provider entity resolution, calibrated materiality,
automatic closed-condition inference, or live-data guarantee. Human review remains required.
