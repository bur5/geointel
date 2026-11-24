# GeoIntel development handover

## Where to resume

Resume the Data Quality and Historical Profiles integration from
`review/dq-historical-b7956e594e9c` at
`3245d1033117d03239e6a9a34d35ce0819320886`. PR #46 is open in draft and its exact head passed
GitHub Actions. It still needs fresh independent review and the applicable Owner and governance
decisions. Use this documentation branch as a reference while working on a separate checkout of
the review head.

| Item | Branch or ref | Exact SHA | Status |
|---|---|---|---|
| Base | `main` | `aaf887030e39a0960323096a7075be783aa97bdf` | Audited remote head |
| PR #30, CI and PostgreSQL reproducibility | `codex/ci-reliability-reproducibility` | `f3f0da952cb60b06198ad50967067adf531cd8b5` | Merged through main |
| PR #33, Data Quality v1 | `codex/data-quality-v1` | `df34d1bdd4f0edf0e30012bd67f1c669b77989f8` | Separate open draft and direct parent of the first integration |
| PR #24, historical conflict profile | `codex/geointel-v0.1.8-historical-conflict-profile` | `d296ee720a45753ef4c1cf49fb23a77120a71303` | Separate open PR, integrated as changes rather than an ancestor |
| PR #46, first integrated implementation | `review/dq-historical-b7956e594e9c` ancestry | `b7956e594e9c609aa4a93e45ff6fc55ff6dcad4b` | Published and locally verified, with defects reproduced later |
| PR #46, correction | `review/dq-historical-b7956e594e9c` | `3245d1033117d03239e6a9a34d35ce0819320886` | Published, tested locally and in CI, awaiting fresh independent review |

PR #33 adds the Data Quality implementation and the source-health monitoring foundation
`904bb1b62ec273d886dc66d0b9b88c3aa3253e6d` on top of main. PR #24 diverged at
`a43ece92adc9c2bdd8652b740b12bdff9623aeee`, before #30. PR #46 overlaps #33 and #24. Keep
their disposition separate from technical review of #46. No new migrations, backfills, provider
activation, or governance changes were made.

[PR #46](https://github.com/bur5/geointel/pull/46) ·
[PR #33](https://github.com/bur5/geointel/pull/33) ·
[PR #24](https://github.com/bur5/geointel/pull/24) ·
[PR #30](https://github.com/bur5/geointel/pull/30)

## Implementation and design

- The first integration applied #24 on #33. It resolved conflicts in
  `src/geointel/pipeline/service.py` and `tests/test_postgres_integration.py`. It retained
  #30's transaction-isolated PostgreSQL fixtures and provider fixes, #33's versioned coverage
  receipts and eligibility projection, and #24's deterministic profiles, taxonomy, normalization
  audit, Red Team checks, and rejection of unsupported numeric forecast bounds.
- UCDP GED is historical evidence even when recently observed. Profiles, base rates, source records,
  and alignment findings remain available for inspection. Assessment inputs use the eligibility
  projection. News remains distinct from evidence and forecasts. Historical release completeness
  can coexist with unknown historical time bounds and never confirms an operational zero.
- `src/geointel/monitoring/service.py` uses historical scope from receipts, including empty and
  failed collections, with persisted historical presence as a fallback. Model-derived forecast and
  uncertainty changes stay diagnostic in those comparisons. Operational health has a separate
  projection for materiality and alert fingerprints. History cannot add or refresh an alert by
  changing that fingerprint. New-event and v1 recency corroboration require newly added providers.
- `src/geointel/coverage.py` requires page counts and the reported received total to agree before
  establishing verified completeness. Partial, restricted, ambiguous and failed retrievals cannot
  establish exact-scope verified zero.
- `src/geointel/pipeline/service.py` uses PostgreSQL savepoints for competing named-row inserts.
  Monitoring finalization takes a target row lock after the analysis commit. Successful comparisons
  proceed in finalization order. A monitoring failure rolls back alert, change, and schedule writes
  while retaining the link to committed analysis. Failed attempts do not become comparison baselines.

## Independent-review findings and reproduction

The prior task reported requested changes from independent review. The GitHub connector returned
an empty review and comment timeline for #46 during this audit. The original reviewer submission,
identity, and any off-platform notes are unavailable here. The findings below are reconstructed
from the reported review instructions and locally reproduced regressions.

| Finding | Regression or control |
|---|---|
| Historical context changed routed model confidence and triggered alerts | `tests/test_historical_conflict_profile.py` covers row count and taxonomy changes, history-only and mixed inputs, refresh protection, and genuine event and signal alerts. |
| Empty and failed historical collections bypassed the row-presence guard | `test_postgres_empty_and_failed_historical_collections_are_diagnostic` uses UCDP verified empty → HTTP 503 → verified empty → HTTP 503. It verifies no creation or refresh, then exercises genuine ACLED and VIEWS outages and confirms history cannot refresh the resulting health alert. |
| Contradictory page evidence manufactured a verified zero | `test_empty_receipt_requires_consistent_page_counts` exercises positive and zero page row counts alongside a zero received total. |
| Existing events from another source incorrectly corroborated newly added single-source events | `test_unchanged_provider_cannot_corroborate_new_events` exercises both the event and recency routes with a distinct-new-provider control. |
| Historical context suppressed genuine operational outages | `test_operational_health_materiality_excludes_historical_health` plus the PostgreSQL outage control. |
| Concurrent first runs hit a duplicate location and could use a stale comparison baseline | `test_postgres_concurrent_target_and_failed_finalization` uses two PostgreSQL sessions and a barrier after the analysis commit. It verifies both completions and one baseline. |
| Failure after committing analysis lost the analysis link | The same PostgreSQL regression injects failure after an alert flush, verifies rollback and the retained committed analysis, then verifies recovery. |

The new focused tests, run against the previous implementation by setting `PYTHONPATH` to an
exact `b7956e5` checkout while collecting tests from `3245d10`, reproduced five failures.
The valid-empty control passed. The selector was
`empty_receipt_requires or unchanged_provider_cannot or operational_health_materiality or empty_and_failed_historical or concurrent_target`
over `tests/test_collection_coverage.py tests/test_monitoring.py tests/test_postgres_integration.py`.

## Verification and reproducibility

Use an isolated PostgreSQL 16 database. The concurrency regression creates and drops its own
temporary schema, so the test database role needs schema creation privileges. Use local fixture
credentials supplied through environment variables. The tested deployment boundary was local
or GitHub CI, with mocked providers and offline validation.

| Command | Verified result |
|---|---|
| `DATABASE_URL="$POSTGRES_TEST_URL" alembic upgrade head` and `alembic current` with the same URL | PostgreSQL migrated through `0008_news_reports` and reported `0008 (head)` |
| `pytest -o addopts='' -q` with `POSTGRES_TEST_URL` | At `3245d10`, 249 passed with zero skips on each of Python 3.11.16 and 3.12.14 |
| `pytest -o addopts='' -q tests/test_postgres_integration.py` | At `3245d10`, 10 passed with zero skips on PostgreSQL 16 |
| `ruff check .`, `ruff format --check .`, `git diff --check b7956e5 HEAD` | Passed at `3245d10` |
| `alembic upgrade head` on a fresh SQLite URL | Reached `0008` at `3245d10` |
| `python -m geointel.validation run five-country-v1 --case spain --json` | The two preserved summaries each have 20 passing assertions from the initial integration work |
| Initial integration on both Python versions and PostgreSQL | At `b7956e5`, 243 passed on each Python with zero skips. PostgreSQL passed eight tests in each of two forward runs and one reverse-order run. The later review fixtures explain the gap in coverage. |
| GitHub Actions at `3245d10` | Run #184 succeeded for both Python jobs and the PostgreSQL integration job |

For the strict type comparison, use Python 3.12.14 with
[the captured package pins](evidence/requirements-py312.txt), then run this identical command in
each exact checkout listed above.

```sh
MYPYPATH=src mypy --strict --no-incremental --config-file pyproject.toml --python-version 3.12 src/geointel
```

Compare diagnostics as multisets of file and message, including error code, ignoring line
numbers. The [normalized evidence](evidence/mypy-diagnostics.json) includes multiplicities.
The initial integration had 401 diagnostics and the correction has 399. Components reported
338 on #24, 382 on #33, and 319 on #30 and main. Every remaining diagnostic matches a component
diagnostic with sufficient multiplicity across the per-diagnostic maximum of the component
counts. The correction introduced zero diagnostics relative to the initial integration and removed
two. Strict mypy still fails on inherited debt.

[CI run #184](https://github.com/bur5/geointel/actions/runs/45297921590) ·
[Offline validation summaries](evidence/offline-validation-summaries.json)

## Owner decisions and next steps

1. Have a fresh independent reviewer inspect the exact #46 head and rerun the routed-model,
   PostgreSQL, and coverage regressions. If heads move, repeat ancestry and CI verification.
2. Decide how to handle genuine operational changes during the initial legacy-to-v1 comparison.
   The first v1 snapshot establishes a baseline, so those changes can go unalerted on that first
   comparison. A policy change requires Owner approval.
3. Decide how to sequence or disposition overlapping PRs #24, #33, and #46. Keep existing PRs
   intact pending that authorization.
4. Keep model-only forecast and uncertainty changes diagnostic when historical collections are in
   scope until the forecast schema can attribute changes to eligible operational inputs. Any
   proposal for historical-provider alerting requires a separate policy decision.
5. Track inherited strict typing debt separately. Concurrent analyses can still execute in parallel
   and persist their own analysis records. A process killed before failure handling can leave a
   running attempt requiring reconciliation. The tested finalization guarantee applies to
   PostgreSQL. Live-provider behavior and production data were outside these verification runs.

## Workspace and archive inventory

The audited repository was `/workspace/geointel`. Its `work` branch points to the published
main ancestor `a43ece92adc9c2bdd8652b740b12bdff9623aeee`. The linked integration worktree
`/workspace/work/geointel` was clean at the #46 head. Detached worktrees `review-main`,
`review-original`, `review-pr24`, `review-pr30`, and `review-pr33` under `/workspace/work`
matched the published commits above. The local `origin/review/…` tracking ref still pointed to
the first integration, while the server branch and PR ref both pointed to the verified correction.
No stashes, untracked project changes, or unreachable commits were found. Earlier reflog-only
checkout positions also resolve within main's ancestry. Generated dependency environments and
cache entries were outside implementation scope.

The object audit recovered two unpublished historical artifacts. They are preserved as patches
rather than runnable source in this branch.

- [Initial conflict snapshot](archive/initial-conflict-snapshot.patch) reproduces tree
  `656cb10f81dfa48f7f25aec0d0ce64d5f1dcf3e4` when applied to the exact #33 head. It contains
  unresolved conflict markers and predates the history alert guard. Its nested unreachable
  trees and three associated blobs are represented by the reconstructed tree.
- [Intermediate pipeline resolution](archive/intermediate-pipeline-resolution.patch) applies to
  that tree and replaces one pipeline blob with `57e880ee075a240b42f876fafb2d353b73fa2637`.
  The resulting archival tree is `5fb8d2a0c96f4074080793ea06370bfcf3f44a3b`. This pairs
  the recovered file with the known snapshot for inspection. There is no evidence that the
  paired tree was ever a checked-out or tested state.

To verify the archives without changing the working tree, use a new temporary index in a
disposable checkout that has the #33 commit. Set `HANDOVER_DIR` to this document's directory.

```sh
archive_index_dir=$(mktemp -d)
export GIT_INDEX_FILE="$archive_index_dir/index"
git read-tree df34d1bdd4f0edf0e30012bd67f1c669b77989f8
git apply --cached --unidiff-zero "$HANDOVER_DIR/archive/initial-conflict-snapshot.patch"
git write-tree
git apply --cached --unidiff-zero "$HANDOVER_DIR/archive/intermediate-pipeline-resolution.patch"
git write-tree
unset GIT_INDEX_FILE
```

The mounted task attachment was the initial instruction text. Its implementation requirements
and subsequent review instructions are reflected here. Raw SQLite databases, transient provider
logs, cache and build artifacts, private environment files, account metadata, and credentials
were excluded. The disposable PostgreSQL instances were already removed. The sqlite validation
JSON was reduced to assertion summaries. Earlier raw mypy output is represented by the later
pinned whole-package comparison. Raw terminal transcripts and any off-platform reviewer
materials were unavailable as standalone artifacts in the accessible workspace. Other agents'
workspaces and private external material were outside this audit.
