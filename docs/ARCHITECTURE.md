# Architecture decision record

## v0.0.3 modular monolith

The modular monolith retains a single transaction for an analysis and its four forecasts. Transport (`api`), domain persistence/schemas, external `connectors`, structured-model `providers`, and `pipeline` orchestration remain replaceable boundaries.

The pipeline now collects two semantically separate record types. `NormalizedEvidence`/`Evidence` represents retrieved historical or observed provider artifacts (currently UCDP); it still does not automatically create an Event. `NormalizedForecastSignal`/`ForecastSignal` represents an external model prediction (currently VIEWS). A signal retains provider record/model identity, geography, issue and target dates, horizon, target, provider-native value/unit/scale, retrieval URL/time, alignment findings, and raw interpretation metadata. It is neither Event nor GEOINTEL Forecast.

Collection is failure-isolated and records a structured outcome for every configured connector, including disabled status. Payloads passed through Analyst, Forecaster, Red Team, and synthesis expose observed evidence, predictive signals, missing/failed sources, and alignment disagreements separately. The Red Team remains mandatory; synthesis must incorporate every non-empty finding. Forecast rows reject updates, so revisions require a new analysis run.

`forecast_signals` is an additive table introduced by migration 0003. PostgreSQL remains the intended persistence layer; CI uses a PostgreSQL 16 service for migrations, application persistence, repeated runs, and immutability. SQLite remains useful for fast portable tests. No PostGIS is required.

## Ensemble and alignment boundary

v0.0.3 provides no numeric ensemble. It makes source/model disagreement visible without inventing weighting. Country, geographic unit, requested horizon, provider horizon, issue date, and target period are retained. Country-level matching is accepted; non-country resolution, location mismatch, or horizon mismatch is flagged and passed to reasoning. No grid/subnational/monthly aggregation occurs because authoritative semantics have not been established.

Future connectors and specialist agents remain out of scope. Research/data connectors only return validated untrusted data; they have no execution, code-writing, secret, database-delete, or deployment authority.

## v0.0.3 operational layer

`NormalizedOperationalEvent` is the ACLED-only observed/reporting boundary and is persisted to an
`Event` linked to its `AnalysisRun`, `Source`, and provider record identifier (migration 0004).
`NormalizedForecastSignal` remains the boundary for both VIEWS and CAST. Reasoning receives
`historical_evidence`, `recent_events`, and `predictive_signals` separately, while the legacy
`evidence` alias remains available. Collection outcomes cover all four connectors and include a
run collection time; failures remain isolated.

The 90-day classification is metadata, not a risk algorithm. No geographic roll-up, predictive
ensemble, causal inference, or corroboration occurs. Provider IDs support conservative exact
within-collection deduplication; cross-source resolution is explicitly deferred.

## v0.0.4 strategic-knowledge layer

Strategic knowledge is a separate domain: `KnowledgeWork` → `KnowledgeSection` → attributed
`StrategicClaim`, with reusable `StrategicConcept` and separately structured `HistoricalCase`
records. Many-to-many tables retain claim/concept/case relationships. None inherits from or is
persisted as `Evidence`, `Event`, or `ForecastSignal`.

The pipeline retrieves bounded structured claims, invokes registered `StrategicLens`
implementations, and passes their outputs under `strategic_context`, separate from
`historical_evidence`, `recent_events`, and `predictive_signals`. `StrategicAnalysis` records bind
lens name/version, retrieved claim and case IDs, retrieval provenance, output, limitations, status,
and timestamp to an `AnalysisRun`. Lens errors are recorded as non-fatal and cannot bypass Analyst,
Forecaster, mandatory Red Team, or synthesis. `LensRegistry` permits additional theories without
pipeline changes; the neutral alternative is only an extensibility demonstration.

## v0.0.5 validation layer

Validation is a meta-evaluation domain, separate from Event, Evidence, ForecastSignal, Forecast, and StrategicAnalysis. A versioned static suite is loaded as strict data, then `ValidationRunner` dependency-injects synthetic connectors and `OfflineModel` into the unchanged normal analysis pipeline. It persists the resulting `AnalysisRun`, followed by a linked `ValidationRun` and one auditable `ValidationResult` per behavioral assertion. Migration 0006 is additive. The per-run source matrix preserves availability, missing/failure, staleness, and mismatch without treating absence as negative evidence. Results are never collapsed into a risk score or country ranking. See [validation](VALIDATION.md).

## v0.1.0 monitoring layer

Monitoring is a separate orchestration/audit domain (`Watchlist`, `WatchlistTarget`,
`MonitoringRun`, `DetectedChange`, `Alert`) layered over the unchanged normal analysis pipeline.
It uses explicit comparable-run rules and structured snapshots, not prose diffs. Migration 0007 is
additive. Source health remains separate from geopolitical state, and alerts retain guardrails,
provenance, deduplication keys, and non-destructive lifecycle history. See [monitoring](MONITORING.md).

## v0.1.1 provider hardening

The operational provider registry, explicit adapter-only verification state, strict normalization,
secret-safe bounded transport, failure taxonomy, and partial collection audit are specified in
[PROVIDERS.md](PROVIDERS.md). Provider health remains operational metadata, not evidence; no
unverified upstream API behavior may be inferred.

# Current-news layer (v0.1.3)

`NewsReport` is a first-class, provenance-bearing media discovery object related to an
`AnalysisRun`. It is structurally separate from `Evidence`, `Event`, `Indicator`,
`ForecastSignal`, strategic claims, and forecasts. The analysis reasoning payload exposes it as
`news_reports`, alongside—not inside—historical evidence, recent events, predictive signals, and
strategic context. Collection health and usable current coverage are operational metadata and
cannot alter geopolitical risk by themselves. Automatic news-to-event/evidence promotion is
deliberately absent.

## Semantic story candidates and conservative corroboration (v0.1.5)

Exact canonical URL identity remains the highest-confidence duplicate layer. The deterministic
`story-similarity-v1` layer compares different URLs using normalized headline Jaccard similarity,
non-generic distinctive tokens, heuristic proper-name overlap, requested-location overlap, and a
72-hour **publication**-time window. It merges only when time plus multiple textual dimensions pass
conservative thresholds (Jaccard >= 0.42 plus three distinctive shared tokens, or location plus two
proper names, two distinctive tokens, and Jaccard >= 0.30). Generic conflict terms are excluded.
Complete-link placement prevents weak transitive bridges. Lower-confidence relationships remain
`possible_same_story_unresolved`, and every decision retains its feature values. False splits are
preferred to false merges. Publication timestamps are never treated as event occurrence times.

Clusters expose report IDs, providers, publisher domains, publication range, match reasons, and
uncertainty. `probable_same_story` is a candidate grouping, not a confirmed common event. Exact
duplicates and explicit wire attribution are `LIKELY_SHARED_REPORTING_CHAIN`. Different providers
have no independence meaning; different domains are `MULTIPLE_DISTINCT_PUBLISHERS_UNRESOLVED`.
`MULTI_SOURCE_CORROBORATED_REPORTING` requires at least two affirmatively `INDEPENDENT` records with
different explicit `reporting_chain_id` values and no detected common wire. It means apparently
independent reporting supports the story, not that the event is proven.

Candidate eligibility also requires a probable cluster, explicit geographic and current temporal
alignment, and no stale/republished classification. It never creates an `Event`, `Evidence`,
`Indicator`, `ForecastSignal`, escalation, or risk adjustment. Clusters and assessments remain
analysis-run metadata, so v0.1.5 needs no schema migration.


## Auditable news discovery pipeline (v0.1.6)

The explicit ordering is provider discovery → raw `NewsReport` → report relevance → operational story clustering (excluding definitively `NOT_RELEVANT` noise) → provenance/dependence assessment → corroboration → candidate eligibility → analyst review. All raw reports remain persisted and all assessments have bounded metadata snapshots; `UNKNOWN` also follows a review path and cannot become eligible merely because its review priority is HIGH. Query match is not geography, publication time is not event time, domains are not independent chains, and no stage automatically creates Event or Evidence. AnalysisRun JSON is used, so v0.1.6 requires no database migration.
