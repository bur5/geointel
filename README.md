# GEOINTEL v0.0.5

GEOINTEL is a geopolitical decision-support and conflict early-warning foundation. v0.0.5 preserves the UCDP/ACLED/VIEWS/CAST pipeline—collection → strategic retrieval/lenses → Analyst → four-category Forecaster → mandatory Red Team → synthesis → immutable persistence—and adds an auditable strategic-knowledge layer. It is not verified intelligence and does not provide personal relocation advice.

## What is included

- Backwards-compatible FastAPI endpoints: `GET /health`, `POST /analysis`, `GET /analysis/{id}`, `GET /forecasts`, and `GET /forecasts/{id}`.
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

All four connectors are disabled by default. UCDP uses `UCDP_ENABLED`, `UCDP_BASE_URL`, `UCDP_API_VERSION`, `UCDP_ENDPOINT_PATH`, `UCDP_ACCESS_TOKEN`, `UCDP_TIMEOUT`, and `UCDP_RETRIES`. VIEWS uses `VIEWS_ENABLED`, `VIEWS_BASE_URL`, `VIEWS_ENDPOINT_PATH`, `VIEWS_TIMEOUT_SECONDS`, and `VIEWS_MAX_RETRIES`. Enabling VIEWS requires both URL fields. Values are environment configuration, never credentials in source control.

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
