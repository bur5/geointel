# GEOINTEL v0.0.2

GEOINTEL is a geopolitical decision-support and conflict early-warning foundation. v0.0.2 keeps the reproducible v0.0.1 pipeline—collection → Analyst → four-category Forecaster → mandatory Red Team → synthesis → immutable persistence—and adds VIEWS model forecasts as an independent predictive input. It is not verified intelligence and does not provide personal relocation advice.

## What is included

- Backwards-compatible FastAPI endpoints: `GET /health`, `POST /analysis`, `GET /analysis/{id}`, `GET /forecasts`, and `GET /forecasts/{id}`.
- Independent UCDP historical-evidence and VIEWS predictive-signal connectors, each with bounded retries, timeouts, validation, provenance, and per-connector outcomes.
- A dedicated `forecast_signals` representation: VIEWS output is never stored as an observed Event or silently promoted to a GEOINTEL probability.
- Deterministic offline reasoning, explicit missing-source and alignment limitations, four conflict categories, mandatory Red Team review, and append-only forecasts.
- SQLite unit/integration tests plus an actual PostgreSQL 16 migration and persistence path in CI.

## Configuration and local run

Python 3.11+ and PostgreSQL 16+ are the intended runtime. Copy `.env.example` to `.env`, set `DATABASE_URL`, then:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
uvicorn geointel.api.app:app --reload
```

Both connectors are disabled by default. UCDP uses `UCDP_ENABLED`, `UCDP_BASE_URL`, `UCDP_API_VERSION`, `UCDP_ENDPOINT_PATH`, `UCDP_ACCESS_TOKEN`, `UCDP_TIMEOUT`, and `UCDP_RETRIES`. VIEWS uses `VIEWS_ENABLED`, `VIEWS_BASE_URL`, `VIEWS_ENDPOINT_PATH`, `VIEWS_TIMEOUT_SECONDS`, and `VIEWS_MAX_RETRIES`. Enabling VIEWS requires both URL fields. Values are environment configuration, never credentials in source control.

### VIEWS live-access status

No authoritative live VIEWS endpoint/response contract could be verified from this development environment. GEOINTEL therefore **does not ship or guess one**. `VIEWS_ENDPOINT_PATH` must identify an operator-supplied, verified adapter that returns the documented internal `{"forecasts": [...]}` contract in `docs/SOURCES.md`. Tests use records explicitly named synthetic. To enable live ingestion, a human must verify current VIEWS documentation/licensing, implement or validate an adapter mapping each official field to that contract, and configure its URL. There is no bundled offline VIEWS value.

A VIEWS outage is isolated: UCDP data remains usable, and vice versa. If both are unavailable, deterministic offline output explicitly reports missing sources and remains unquantified. `collection_metadata.connector_outcomes` reports attempted/disabled/succeeded/failed status, record count, and a bounded safe failure reason.

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

There is no verified direct live VIEWS integration, official VIEWS aggregation algorithm, or ensemble weighting in v0.0.2. Subnational/grid or mismatched-horizon signals are retained and flagged, never silently aggregated. Provider-native predictions retain their stated unit/scale and are not reinterpreted. There is also no live LLM/news feed, authentication, rate limiting, PostGIS, calibration/backtesting, UI, alerting, or deployment automation. `POST /analysis` remains synchronous; do not expose it to untrusted networks as-is.

See [architecture](docs/ARCHITECTURE.md), [forecasting](docs/FORECASTING.md), [sources](docs/SOURCES.md), [agent rules](docs/AGENT_RULES.md), and [security](docs/SECURITY.md).
