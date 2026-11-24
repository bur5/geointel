# Early Warning v1 review and validation evidence

This is a reconstruction from the development request, checked-in regressions,
recorded local execution results and verified GitHub metadata. It contains no
provider data, environment secrets, original database contents or raw session logs.

## Independent findings and how to reproduce them

The initial review input was commit `2972262dd7955328c2f9f0b96d99f1394685f855`
on [PR #47][pr]. The correction is `d69e9dfe8f2aa9641dac9ba20cf93a85db5e81a9`.
Run the named tests on the correction. The initial commit is reachable separately
for comparing implementation behavior. GitHub returned no review submissions or
inline review threads for PR #47 at audit time. This table records the issues the
Owner relayed and their regression coverage.

| Reported finding | Reproduction on the corrected commit and expected result |
| --- | --- |
| Unrelated activity could corroborate CRITICAL | `test_activity_corroboration_requires_review_of_the_exact_feed_and_target`. Reject absent, mismatched and unversioned mappings. Forecast-only evidence remains WARNING for the fixture, missing required activity yields INSUFFICIENT_DATA, and a valid matching feed can corroborate CRITICAL. A mapping version change starts a new stream. |
| Advisory persistence tests skipped in PostgreSQL CI | Inspect the workflow's PostgreSQL invocation and [job logs][pg]. Both database test files run, including advisory concurrent retry, rollback, migration and real runtime-role cases. |
| Receipt ID could be reused across queries or windows | `test_operational_receipt_is_bound_to_collection_filter_country_and_window`. Change any bound dimension while retaining the ID and expect rejection. An audited, exact empty window establishes zero. |
| Boolean forecasts could become `1.0` or `0.0` | Run `test_views_ingestion_rejects_json_booleans_before_float_coercion`, `test_boolean_observation_rejected_even_with_validation_bypass`, and the normalized/persisted adapter cases. Boolean JSON fails while the numeric endpoints remain accepted. |
| Documented runtime grants omitted checkpoint creation | `test_postgres_runtime_login_resumes_checkpoint_and_cannot_mutate_history`. A dedicated non-owner login can insert the checkpoint, advance it and recover after reconnecting. History deletion is denied. The grant set also runs the other advisory persistence cases. |
| Missing deployable Alembic schema | `test_postgres_migration_install_upgrade_and_rollback`. A new disposable PostgreSQL database reaches head, advisory metadata matches, a write succeeds, downgrade to `0008` drops advisory tables and keeps the prior schema, and re-upgrade recreates empty tables. |
| PR #46 status could be mistaken for exact filtered completeness | `test_complete_status_cannot_replace_an_exact_operational_audit`. Reject a coverage-only status, missing proof, wrong filter, broad dates, media/historical audit kind, incomplete pagination, restrictions and unreconciled counts. |
| Revising validation could compromise replay, concurrency or checkpoints | Run the concurrent retry, reordered-feed, cutoff, late-evidence, rollback, recovery, and replay tests in `tests/test_early_warning.py`. Exact retries return the saved snapshot. Late evidence cannot rewrite the first occurrence, and replay cannot emit live transition IDs. |

## Recorded validation

| Implementation | Check | Recorded outcome |
| --- | --- | --- |
| Original `2972262` | Local full suite with PostgreSQL 16 | 222 passed |
| Original `2972262` | Advisory plus PostgreSQL focused suite | 45 passed |
| Original `2972262` | Monitoring, API, domain and provider focused suite | 89 passed |
| Original `2972262` | Ruff lint, Ruff format and scoped mypy | Passed |
| Original `2972262` | [GitHub Actions run 178][initial-ci] | Success |
| Corrected `d69e9df` | Local full suite on Python 3.11.16 and 3.12.14, each using PostgreSQL 16 | 231 passed on each, zero skips, existing Starlette TestClient deprecation warning |
| Corrected `d69e9df` | Local PostgreSQL focused suite | 52 passed, zero skips, same warning |
| Corrected `d69e9df` | [GitHub Actions run 180][ci] | Python 3.11, Python 3.12 and PostgreSQL jobs succeeded. [PostgreSQL job][pg] ran both requested files and reported 52 passed with zero skips |
| Corrected `d69e9df` | Ruff lint and format, scoped mypy on three advisory modules, compileall, Git diff checks | Passed |
| Corrected `d69e9df` | Clean install through `0009_early_warning`, rollback to `0008`, and re-upgrade | Passed on disposable PostgreSQL 16 and SQLite. PostgreSQL advisory metadata comparison found no differences |
| Corrected `d69e9df` | Offline validation smoke, `five-country-v1` suite version 1.0.0, Spain only | Synthetic fixture, 20 assertions passed, 0 failed, 0 errors, 0 not applicable |
| Corrected `d69e9df` | Application health after SQLite migration | HTTP 200, status `ok` |

The repository-wide PostgreSQL `alembic check` returned the same five differences
on both commits. The migration-created indexes `ix_events_source_record`,
`ix_strategic_analyses_run`, `ix_validation_results_run`, and
`ix_validation_runs_analysis` are missing from ORM metadata. The comment on
`locations.geometry_wkt` also differs. This drift is outside the advisory
migration. Preserve it as a separate maintenance issue.

## Reproduction commands

Use a checkout pinned to the correction and a fresh virtual environment for each
Python version. Set `DATABASE_URL` to a disposable PostgreSQL 16 database using
local test credentials. The test fixture login must be able to create/drop disposable
databases, schemas and roles. Advisory operations within the permission tests
authenticate separately as least-privilege users. Never direct these tests at a
shared or production database.

```bash
python -m pip install -e '.[dev]'
python -m pip install mypy
alembic upgrade head
export POSTGRES_TEST_URL="$DATABASE_URL"
python -m pytest -o addopts='' -q -rs
python -m pytest -o addopts='' -q -rs tests/test_postgres_integration.py tests/test_early_warning.py
ruff check .
ruff format --check .
mypy --follow-imports=silent src/geointel/early_warning*.py
python -m compileall -q src tests migrations
git diff --check
git diff --check origin/main...HEAD
```

On a new disposable SQLite database or a separate disposable PostgreSQL database,
run the migration sequence below. The downgrade deletes advisory history in that
database. The PostgreSQL test suite exercises the same sequence automatically.

```bash
alembic upgrade head
alembic current
alembic downgrade 0008
alembic current
alembic upgrade head
alembic current
```

Point `DATABASE_URL` at a fresh disposable SQLite database for the offline smoke command.

```bash
python -m geointel.validation run five-country-v1 --case spain --json
```

The results cover fixture behavior, database constraints and CI reproducibility.
No live provider measurement, production access, or predictive calibration was
part of the validation.

[pr]: https://github.com/bur5/geointel/pull/47
[initial-ci]: https://github.com/bur5/geointel/actions/runs/45260600794
[ci]: https://github.com/bur5/geointel/actions/runs/45297513552
[pg]: https://github.com/bur5/geointel/actions/runs/45297513552/job/138121562352
