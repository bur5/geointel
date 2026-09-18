# Architecture decision record

## v0.0.1 modular monolith

A modular monolith is preferable to premature services: one transactional boundary guarantees that an analysis and its four forecasts persist together, while connector/model protocols retain replaceable boundaries. The requested long-term directory map is represented as logical Python packages rather than independently deployed services. Transport (`api`), domain/database, external connectors, structured-model providers, and orchestration pipeline do not import inward from API.

The pipeline creates a unique UUID analysis run, collects normalized evidence without promoting it automatically to an event, obtains structured Analyst and Forecast outputs, mandates an adversarial Red Team pass, asks Meta Analyst synthesis to incorporate named critiques, and persists the synthesis and append-only forecasts. Provider names and pipeline version—but no credentials—are retained.

PostgreSQL is the runtime database. Portable WKT makes location storage useful without requiring PostGIS locally; a future migration can add a PostGIS geometry column. JSON artifacts can later gain pgvector embeddings without changing their semantic identity.

## Extension boundaries

`EvidenceConnector` admits UCDP, ACLED, CAST, VIEWS and economic/institutional feeds. `StructuredModel` admits hosted/local models selected by conceptual role rather than hard-coded model ID. A future knowledge interface should represent Book → Chapter → Claim/Concept/Historical Case/Prediction/Methodological Rule while storing only licensed metadata and user-authorized excerpts, never bundled copyrighted books.

Future specialist agents (data, military, economic, demographic, historian, Kissinger/balance-of-power, realist and alternative/institutional lenses) should issue blinded independent first-round assessments. Forecaster follows; Red Team sees all; Meta Analyst reconciles them. Voice and a future Next.js UI remain adapters to the same API. Exit-risk must be a separate bounded domain and must never be inferred directly from geopolitical forecast probability.
