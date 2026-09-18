# GEOINTEL v0.0.1

GEOINTEL is a personal geopolitical decision-support and conflict early-warning foundation. This release proves a reproducible vertical slice: evidence collection → analyst → four-category forecast → mandatory red team → synthesis → immutable persistence → API retrieval. It does **not** claim to be verified intelligence or provide personal relocation advice.

## What is included

- FastAPI endpoints: `GET /health`, `POST /analysis`, `GET /analysis/{id}`, `GET /forecasts`, `GET /forecasts/{id}`.
- SQLAlchemy domain model for locations, sources, evidence, events, indicators, scenarios, forecasts, and analysis runs; Alembic migration; PostgreSQL runtime.
- A bounded, configurable UCDP adapter with normalization, retries, timeouts, provenance and explicit failures. No undocumented endpoint is assumed.
- An AI-independent `ModelRouter` and deterministic offline provider. Offline output refuses invented probabilities and clearly marks missing live evidence.
- Four distinct conflict categories and a mandatory red-team/synthesis stage.

## Architecture

The code is a modular monolith under `src/geointel`: `api` is transport, `domain` owns schemas/persistence, `connectors` isolates external data, `providers` abstracts structured models, and `pipeline` orchestrates the run. See [architecture](docs/ARCHITECTURE.md), [forecasting](docs/FORECASTING.md), [sources](docs/SOURCES.md), [agent rules](docs/AGENT_RULES.md), and [security](docs/SECURITY.md).

## Requirements and configuration

Python 3.11+ and, for normal operation, PostgreSQL 16+. Copy `.env.example` to `.env` and fill only required values. `DATABASE_URL` is the only value needed for PostgreSQL. Never commit `.env`. UCDP remains disabled until its current documented endpoint/access requirements are configured in an integration implementation; its base URL/version/token variables reserve a safe configuration path. No model API credential is required in v0.0.1.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
# Set DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DB in .env
alembic upgrade head
uvicorn geointel.api.app:app --reload
```

Run tests with `pytest`; lint with `ruff check .`. Tests use in-memory SQLite and no network/API keys.

## Run with Docker

```bash
docker compose up --build
curl http://localhost:8000/health
```

Compose applies migrations before serving. Its database password is deliberately local-development-only; replace it outside an isolated workstation.

## Spain control analysis

```bash
curl -sS http://localhost:8000/analysis -H 'content-type: application/json' -d '{
  "location":"Spain",
  "question":"Analyze the risk of organized political violence in Spain over the next 12 months. Separate interstate conflict, internal armed conflict, one-sided violence and major political violence. Identify evidence for and against escalation, historical base rates, major unknowns, and conditions that would materially change the assessment.",
  "horizon_months":12
}'
```

The shipped offline provider produces four low-confidence, unquantified assessments because it has no current evidence or calibrated base rates. This is intentional anti-fabrication behavior, not a substantive Spain forecast. Each invocation creates a new analysis run and new forecasts.

## Known limitations / credentials still required

- No live LLM, current-news, calibrated base-rate, PostGIS, pgvector, authentication, job queue, monitoring/alerts, UI, strategic-library RAG, voice, or exit-risk module.
- `POST /analysis` is synchronous. Add authorization and rate limiting before exposure to untrusted networks.
- UCDP's endpoint is intentionally not guessed. Live use requires confirmation of current provider documentation, endpoint implementation, and possibly `UCDP_ACCESS_TOKEN`; failures must remain non-fatal to the wider pipeline.
- SQLite is supported only for development/tests; production persistence target is PostgreSQL. Geographic WKT is a migration bridge, not spatial querying.
