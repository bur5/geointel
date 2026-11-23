# GEOINTEL v0.1.7

GEOINTEL is a geopolitical decision-support and conflict early-warning foundation. v0.1.0 preserves the UCDP/ACLED/VIEWS/CAST pipeline—collection → strategic retrieval/lenses → Analyst → four-category Forecaster → mandatory Red Team → synthesis → immutable persistence—and adds an auditable strategic-knowledge layer. It is not verified intelligence and does not provide personal relocation advice.

## What is included

- Backwards-compatible FastAPI endpoints: `GET /health`, `POST /analysis`, `GET /analysis/{id}`, `GET /forecasts`, and `GET /forecasts/{id}`.
- [Read-only dashboard API v1](docs/DASHBOARD_API.md) for observations, forecasts, and coverage.
- Independent UCDP historical-evidence and VIEWS predictive-signal connectors, each with bounded retries, timeouts, validation, provenance, and per-connector outcomes.
- A dedicated `forecast_signals` representation: VIEWS output is never stored as an observed Event or silently promoted to a GEOINTEL probability.
- Deterministic offline reasoning, explicit missing-source and alignment limitations, four conflict categories, mandatory Red Team review, and append-only forecasts.
- SQLite unit/integration tests plus an actual PostgreSQL 16 migration and persistence path in CI.
- A separate, attributed strategic-knowledge library with bounded JSON ingestion, deterministic lexical/structured retrieval, an auditable generic lens interface, and a restrained Kissinger lens. Strategic claims and lens interpretations are never evidence, events, predictive signals, or probabilities.

## Configuration and local run

Python 3.11+ and PostgreSQL 16+ are the intended runtime. Copy `.env.example` to `.env`, set `DATABASE_URL`, then:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
uvicorn geointel.api.app:app --reload
```

All four connectors are disabled by default. Set `UCDP_MODE=official_api` with a UCDP token and
explicit dataset version for official GED access. Set `ACLED_MODE=official_api` and/or
`CAST_MODE=official_api` with myACLED username/password secrets for official Event/CAST access.
VIEWS remains operator-adapter-only. Values are environment configuration and credentials belong
only in deployment secret management, never source control. See [provider operations](docs/PROVIDERS.md).

### VIEWS live-access status

No authoritative live VIEWS endpoint/response contract could be verified from this development environment. GEOINTEL therefore **does not ship or guess one**. `VIEWS_ENDPOINT_PATH` must identify an operator-supplied, verified adapter that returns the documented internal `{"forecasts": [...]}` contract in `docs/SOURCES.md`. Tests use records explicitly named synthetic. To enable live ingestion, a human must verify current VIEWS documentation/licensing, implement or validate an adapter mapping each official field to that contract, and configure its URL. There is no bundled offline VIEWS value.

Connector outages are isolated: successful sources remain usable. If all are unavailable, deterministic offline output explicitly reports missing sources and remains unquantified. `collection_metadata.connector_outcomes` reports attempted/disabled/succeeded/failed status, record count, and a bounded safe failure reason.

## Spain control case

```bash
curl -sS http://localhost:8000/analysis -H 'content-type: application/json' -d '{
  "location":"Spain",
  "question":"Analyze the risk of organized political violence in Spain over the next 12 months. Separate interstate conflict, internal armed conflict, one-sided violence and major political violence. Identify evidence for and against escalation, historical base rates, major unknowns, and conditions that would materially change the assessment.",
  "horizon_months":12
}'
```

Spain is an anti-catastrophizing control, not a hard-coded conclusion. Repeated requests create distinct runs and retain prior forecasts.

## Verification

```bash
ruff check .
ruff format --check .
python -m compileall -q src tests migrations
DATABASE_URL=sqlite:///./migration-check.db alembic upgrade head
pytest
```

GitHub Actions runs these checks on Python 3.11 and 3.12, performs startup/health probes, and separately migrates PostgreSQL 16 and verifies connection, repeated persistence, and forecast immutability.

## Known limitations

There is no verified direct live VIEWS integration, official VIEWS aggregation algorithm, or ensemble weighting in v0.0.3. Subnational/grid or mismatched-horizon signals are retained and flagged, never silently aggregated. Provider-native predictions retain their stated unit/scale and are not reinterpreted. There is also no live LLM/news feed, authentication, rate limiting, PostGIS, calibration/backtesting, UI, alerting, or deployment automation. `POST /analysis` remains synchronous; do not expose it to untrusted networks as-is.

See [architecture](docs/ARCHITECTURE.md), [forecasting](docs/FORECASTING.md), [sources](docs/SOURCES.md), [agent rules](docs/AGENT_RULES.md), and [security](docs/SECURITY.md).

## v0.1.5.1 news-relevance hotfix

News discovery now follows an explicit, deterministic review path:

`NewsReport` → `NewsRelevanceAssessment` → `StoryCluster` → source/reporting-chain
assessment → candidate indicator → human/analyst validation → a possible future explicit
Evidence/Event process.

Relevance is a transparent discovery heuristic, not truth or event confirmation. Corroborated
reporting is not a confirmed event, and a candidate indicator is not Evidence or an Event. Article
volume is not risk. Query geography records collection intent; it is not demonstrated story
geography unless title, description, or source metadata supports it. Delayed NewsAPI discovery
leads remain separate from validated current operational coverage.

## v0.0.3 operational early-warning sources

The source boundary is explicit: **UCDP is historical conflict evidence; ACLED is recent
observed/reported operational event evidence; VIEWS is an independent predictive signal; and
CAST is a short-term predictive signal.** ACLED is persisted as `Event`, while CAST and VIEWS
are persisted as `ForecastSignal`; neither kind is promoted to a GEOINTEL forecast or treated as
confirmation of the other.

ACLED and CAST are disabled by default. This development environment could not authenticate to
and verify current authoritative API/access documentation (the documentation lookup returned an
authorization failure). Consequently GEOINTEL deliberately ships no upstream endpoint,
authentication convention, pagination rule, or claimed provider schema. Operators may configure
`ACLED_BASE_URL`/`ACLED_ENDPOINT_PATH` and `CAST_BASE_URL`/`CAST_ENDPOINT_PATH` only for reviewed
adapters implementing the internal contracts documented in `docs/SOURCES.md`. Timeout/retry
settings are bounded. A human must verify current access, field mappings, and licensing before
production enablement; no credentials are currently sent by these adapters.

Operational event dates are deterministically labelled `current_window` when they are from
retrieval time through the preceding 90 days; older records are `historical` and future-dated
records are mismatches. Geographic and forecast-horizon mismatches are surfaced, not aggregated.
Exact provider-ID duplicates are removed within a collection. Similar or cross-source reports are
not merged; entity resolution remains future work. There is no automatic ensemble weighting.


## v0.0.4 strategic knowledge

Operator-provided, copyright-safe structured JSON can represent works, sections, attributed claims, reusable concepts, and historical cases. GEOINTEL never downloads books. Retrieval is deterministic lexical/structured matching (not semantic or embedding search), and every result retains claim/work/author provenance and retrieval reasons. The Kissinger lens asks questions about equilibrium, durable interests, commitments, order, revision, and off-ramps, but has no authority over empirical inputs. Lens failure and an empty library are non-fatal. See [strategic knowledge](docs/STRATEGIC_KNOWLEDGE.md).

## v0.0.5 five-country validation

GEOINTEL now includes a first-class, offline behavioral validation layer. The versioned `five-country-v1` suite uses deterministic **synthetic** conditions for Spain, Georgia, Taiwan, Serbia, and Nigeria. These cases are heterogeneous tests, **not a risk ranking or real-world forecast**, and encode no required risk labels or political recommendations. Validation runs fixture inputs through the normal pipeline and `OfflineModel`, then persists a linked source matrix and individual assertion results via additive migration 0006.

```bash
python -m geointel.validation run five-country-v1
python -m geointel.validation run five-country-v1 --case spain
python -m geointel.validation run five-country-v1 --json
```

Assertions cover taxonomy, provenance, epistemic separation, missing/failing inputs, disagreement, stale/geographic mismatch, uncertainty, mandatory bias-aware Red Team review, immutable/repeated history, deterministic structure, deduplication boundaries, and false-positive restraint. Output provides pass/fail/error/not-applicable counts but no single score. See [validation](docs/VALIDATION.md).


## v0.1.0 monitoring and alerts

Watchlists and country targets now drive repeatable UTC cadence evaluation through the normal
`AnalysisPipeline`. Every attempt, comparable-run decision, structured detected change, and alert
decision is auditable. First runs establish non-alerting baselines; deterministic materiality, Red
Team guardrails, source-health separation, SHA-256 deduplication, and open/resolved history prevent
alert spam and avoid treating outage, theory, or isolated events as escalation.

```bash
python -m geointel.monitoring create-watchlist "Operations"
python -m geointel.monitoring add-target WATCHLIST_UUID ISO-ID "Display name"
python -m geointel.monitoring run-target TARGET_UUID
python -m geointel.monitoring run-due
python -m geointel.monitoring list-alerts
```

Migration 0007 adds monitoring tables and indexes without modifying prior migrations. Tests remain
offline. There is deliberately no live scheduler, notification provider, political ranking, or
decision automation. See [monitoring](docs/MONITORING.md).

## v0.1.1 live-data hardening

All four providers now have an explicit secret-free capability registry and integration mode.
They remain disabled by default and operator-adapter-only because authoritative contracts could
not be accessed from this environment; no endpoint, authentication, pagination, or field semantic
was guessed. Shared utilities add HTTPS/SSRF validation, redirect refusal, bounded JSON transport,
retry/rate-limit failure taxonomy, sanitization, collection audits, and loop-safe pagination.
Use `python -m geointel.providers capabilities` or read-only `GET /providers`; neither performs live
collection. See [provider operations](docs/PROVIDERS.md).

## v0.1.2 verified live providers

UCDP GED, ACLED Event, and ACLED CAST now provide opt-in official API modes with mocked contract
tests. UCDP uses its versioned `gedevents` contract and token header. ACLED and CAST share an
in-memory OAuth client and hardened transport while retaining separate Event and ForecastSignal
normalization. ACLED Event uses cursor pagination in advance of the October 1, 2026 transition;
CAST values remain monthly event counts, never probabilities. VIEWS remains adapter-only because
its exact current technical contract could not be independently retrieved. Explicit bounded
connectivity probes are available through `python -m geointel.providers check-live PROVIDER`.


## News query intelligence (v0.1.6)

NewsAPI is a **discovery-only** source. Its Developer plan is delayed and intended only for development/testing. A deterministic, request-budget-bounded query plan combines geography with small organized-violence signal families; this improves discovery efficiency, not truth, and query terms never count as article evidence. Every report is retained with a bounded safe relevance audit snapshot. Conservative `UNKNOWN` items enter a HIGH/MEDIUM/LOW analyst review queue; that priority is information-quality triage, not event probability or geopolitical risk. Relevance and candidate indicators are neither Events nor Evidence, and news availability never establishes validated current operational coverage.

## Corrective provider and discovery hardening (v0.1.6.1)

Official UCDP requests now fail closed through a reviewed country-identity table and send the
numeric Gleditsch-Ward code as `Country`; the original requested geography and resolved provider
identifier remain separate in audit/provenance. Annual GED is historical/base-rate material.
`UCDP_DATASET_ROLE=candidate_recent` explicitly labels a configured Candidate version as recent,
approximately monthly-lag observed-conflict material—not real-time intelligence. Versions are
never combined without record provenance, and neither dataset's absence proves absence of violence.

News relevance recognizes only explicitly mapped subnational entities (currently Catalonia and
Tarragona for Spain) and audits the matching entity. A violence term plus a political actor or
campaign term plus supported geography is a potential political-violence *discovery* lead; motive,
occurrence, Event, and Evidence status are never inferred. NewsAPI families rotate by persisted
analysis-run sequence with deterministic round-robin selection while retaining the request budget.
GDELT audit metadata retains its 90-day window, non-paginated ArticleList truncation, fresh-fetch
status, and success/rate-limit distinction; GDELT remains a discovery sensor only.

## Historical base-rate features (v0.1.7)

Annual UCDP GED observations are historical context, never current operational
violence or predictive signals. Explicit provenance temporal roles separate
current observations, historical observations, provider predictions and media
leads. Unclassified structured evidence remains in the audit store without
being promoted to current evidence. Historical collection alone cannot establish
current operational coverage or escalation.

`collection_metadata.historical_base_rate_summary` and the typed analyst output
contain deterministic `historical-observations-v1` features. See
[the historical feature contract](docs/HISTORICAL_BASE_RATES.md). These are inputs
for future calibrated forecasting models, not probabilities or model authority.
