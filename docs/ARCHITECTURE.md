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
