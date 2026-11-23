# Dashboard integration reconstruction

The isolated branch `codex/rebuild-dashboard-pr42-pr43` starts from common base
`aaf887030e39a0960323096a7075be783aa97bdf`. It fast-forwards to PR #42
`1dca5a12573191670d8a2a778112eaab7cffe4d2` and joins PR #43
`5ebbf6718a3e8b6be7b433bca65152d3ce3131fb` in a local history-preserving
commit `80a63844b0564a434ce5541d28012682f065bf7b`. The source trees combined
without conflicts. The adapter changes are in the subsequent candidate commit.

GitHub could not resolve previously reported candidate
`2f0a5b3bf9cb1a5c5494803c6169077fa7521bdf`. A code-level comparison with that
candidate is unavailable. The reproducible comparison is against the two
verified PR trees and their local history join.

## Changes relative to the source revisions

- API mode is the default. Demo mode remains explicitly selectable and uses PR #43's existing
  labelled fixtures. API requests use PR #42's read-only dashboard prefix and paginated envelopes.
- Countries use the ISO 3166-1 numeric-to-alpha-3 crosswalk from `pycountry` 26.2.16. Names and
  native units on stored records come from API geography and provenance. The map is neutral in API mode.
  Global lists retain unresolved and non-country records.
- Each panel validates and renders its own response. Missing records, end of results, failed or
  malformed responses and retries are visible. Returning to a view or changing countries cancels
  in-flight requests. Pagination follows the API's bounded offset and retains previous pages.
- Coverage describes latest stored records. Observations retain source distinctions and reported
  fatality fields. Provider forecasts retain issuance, target dates, horizons, native units and
  scale, and both freshness and target period status. Assessments retain nullable stored bounds,
  confidence, original horizon and issuance. The dashboard contract omits private analysis text and
  does not supply assessment target dates, provider uncertainty intervals, or live provider health.

## Security and data isolation

**Production blocker.** The existing validation CLI uses `DATABASE_URL` and writes synthetic
records through the ordinary analysis pipeline. Dashboard queries do not exclude validation runs
or inspect synthetic provenance. API mode cannot determine whether a shared database contains
synthetic artifacts. Use separate databases and credentials for validation and any production
workspace. An existing shared database needs a provenance and segregation audit before it can
serve production evidence. In a separate disposable PostgreSQL run, the Georgia validation case returned one operational
observation, two provider forecasts and four GEOINTEL assessments through ordinary dashboard
reads. The browser fixture below is seeded in its own disposable database and the development UI
explicitly labels it as synthetic.

Use `geointel.api.app:dashboard_app` behind a gateway for any future controlled evaluation.
The read-only route surface excludes legacy analysis, provider and forecast routes. Application-level
authentication and authorization are absent, and the ASGI route list does not enforce database
privileges. Independently review gateway access controls, read-only database grants, provider
licensing, and disclosure of identifiers or free-text source fields before exposing data. Offset
pagination can shift under concurrent writes and global reads can scan large tables. No public
deployment, independent review, or security approval took place.

## Verification results

| Check | Result |
| --- | --- |
| Python 3.11.16 with PostgreSQL 16.16 | 203 passed |
| Python 3.12.14 with PostgreSQL 16.16 | 203 passed |
| Focused PostgreSQL integration suite on Python 3.12 | 7 passed |
| Ruff lint, Ruff format and Python compilation | Passed |
| TypeScript check and frontend build on Node.js 24.19.0 | Passed |
| Playwright with Chromium 151, including live ASGI and PostgreSQL | 16 passed |

Both Python runs emitted a Starlette TestClient deprecation warning for its HTTPX integration.

## Independent review and reproduction

1. Fetch the integration branch and PR heads. Compare the checked-out tip to the remote ref.
   `git show -s --format='%H %P' 80a63844b0564a434ce5541d28012682f065bf7b`
   should list the exact PR #42 and #43 revisions as parents. To fetch and review:

   ```sh
   git fetch origin refs/heads/codex/rebuild-dashboard-pr42-pr43:refs/review/geointel-candidate \
     refs/pull/42/head:refs/review/geointel-pr42 refs/pull/43/head:refs/review/geointel-pr43
   git switch --detach refs/review/geointel-candidate
   git ls-remote origin refs/heads/codex/rebuild-dashboard-pr42-pr43
   git rev-parse HEAD
   git merge-base refs/review/geointel-pr42 refs/review/geointel-pr43
   git diff 80a63844b0564a434ce5541d28012682f065bf7b HEAD
   ```

   Verify their
   `git merge-base` equals the common base above, and inspect
   `git diff 80a63844b0564a434ce5541d28012682f065bf7b HEAD` for the adapter delta.
2. In separate Python 3.11 and 3.12 environments, install `python -m pip install -e '.[dev]'`.
   Run `ruff check .`, `ruff format --check .`, and
   `python -m compileall -q src tests migrations frontend/tests/support`.
   The repository has no configured Python static type checker.
3. Start disposable PostgreSQL 16 on loopback. For example:

   ```sh
   docker run --rm -d --name geointel-dashboard-review \
     -e POSTGRES_PASSWORD=review-local-only -p 127.0.0.1:55432:5432 postgres:16
   docker exec geointel-dashboard-review pg_isready -U postgres
   export DATABASE_URL=postgresql+psycopg://postgres:review-local-only@127.0.0.1:55432/postgres
   alembic upgrade head
   POSTGRES_TEST_URL="$DATABASE_URL" pytest
   POSTGRES_TEST_URL="$DATABASE_URL" pytest tests/test_postgres_integration.py
   ```

4. Use a fresh fixture database for actual browser integration. Start the app in a dedicated terminal:

   ```sh
   docker exec geointel-dashboard-review createdb -U postgres geointel_browser_test
   export DATABASE_URL=postgresql+psycopg://postgres:review-local-only@127.0.0.1:55432/geointel_browser_test
   alembic upgrade head
   python frontend/tests/support/seed_dashboard.py
   uvicorn geointel.api.app:dashboard_app --host 127.0.0.1 --port 8014
   ```

5. In another terminal, run:

   ```sh
   cd frontend
   npm ci
   npm run lint
   npm run build
   npx playwright install chromium
   GEOINTEL_DASHBOARD_ORIGIN=http://127.0.0.1:8014 GEOINTEL_ASGI_TEST=1 \
     VITE_GEOINTEL_VALIDATION=1 npm test
   ```

   Playwright reads all five series and coverage through Vite and the real ASGI app, verifies
   geography, native units, stale and expired records, empty responses and pagination, and checks
   that legacy paths and writes are unavailable. Separate browser tests inject malformed and
   failed responses and exercise retry. Stop the ASGI process and run
   `docker stop geointel-dashboard-review` to discard the test databases.

6. To verify the production isolation blocker, migrate a **separate disposable database**,
   then run `python -m geointel.validation run five-country-v1 --case georgia --json`.
   Under that database only, compare the returned analysis run ID with
   `provenance.analysis_run_id` from the dashboard's `observations`, `forecasts`, and
   `assessments` endpoints scoped to `country=GEO`.
