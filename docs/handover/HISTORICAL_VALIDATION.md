# Historical Validation implementation and verification

## Published implementation history

| Commit | Scope and status |
| --- | --- |
| `9d48fee7d2f3802ba54cf8c6f18bc096c9853baa` | PR #44 foundation for fold audits, protocol, and discrimination utilities. |
| `83fab3a7f16413dde3090925b2b8d2f5b3b60ba9` | PR #44 fail-closed historical benchmark validation. |
| `d9c032567518f3f43d5e62ff224e2120b494d11d` | PR #44 replay and study registration clock safeguards. |
| `3516810c74763a4c21d2c858969b24970723cf3f` | PR #44 registered panel and evidence-mode binding. Original schema v3 implementation and parent of the repair. |
| `3d537b31d0fd4bfde922f108945c96a339063988` | PR #45 initial repair. Independent verifier, structural v4, and global snapshot consistency. Locally verified, followed by compatibility findings. |
| `8743b4025821ecdf23628a91c5a82091d2a24f90` | PR #45 compatibility correction. Directional source corroboration, genuine v3 fixtures and explicit v4 migration, and explicit unsupported scoring. Locally verified, CI green, followed by the deferred-evidence finding. |
| `44f405b43514f4032f3f5a6d7ba9665bd81d7ffd` | PR #45 deferred evidence correction. Locally verified, CI green, awaiting fresh independent acceptance. |

Application code is under `src/geointel/historical_validation/`. The foundation
has technical and illustrative case notes in `docs/HISTORICAL_VALIDATION.md` and
`docs/HISTORICAL_VALIDATION_CASES.md`. The report contract and future adapter
requirements are in
[the published benchmark documentation](https://github.com/bur5/geointel/blob/44f405b43514f4032f3f5a6d7ba9665bd81d7ffd/docs/HISTORICAL_BENCHMARK_REPORT.md).

## Findings and resolutions

| Reported at | Finding | Repair and regression evidence |
| --- | --- | --- |
| #44 head | A serialized report could claim verified panel coverage after adding an audit for a missing slot. A self-asserted publication record could likewise confer verified status. | Structural parse leaves verification unverified. `verify_report_v1` recomputes audit membership from the original request and verifies independent registration, roster, mode, publication and source declarations. Tests reject substituted audits, forged statuses and unsupported publication claims. |
| #44 head | A snapshot could carry contradictory availability metadata across folds or between development and evaluation while individual cutoff checks passed. | Report-level inventory compares normalized snapshot IDs, timestamps, evidence references and populated versions across folds and roles. Geography is retained in case identity. Tests cover repeats, aliases, conflicts, UTC offsets, geography, and freeze boundaries. |
| First #45 candidate | Source matching required exact metadata equality even where the original request lacked optional fields. Migrated legacy reports could serialize newer fields while labeled v3. | Directional corroboration requires every populated declaration to match. Authenticated evidence can supply missing optional fields without altering request digests. Genuine v3 wire fixtures migrate to v4 and downgrade embedded claims. |
| First #45 candidate | Publication-time eligibility needed a separate boundary from window maturity, per-case outcome completeness and actual scoring. | The verifier explicitly returns `scoring_status="unsupported"`. Timely publication cannot override maturity, panel completeness or scoring inputs. The manifest schema keeps comparisons empty. |
| Second #45 candidate | Reports saved before publication evidence existed failed verification after it was resolved. The materialized rebuild included evidence absent in the original report digest. | Evidence is fully checked and returned separately on the verification result. Archive comparison preserves original omissions. Tests cover genuine v3 and native v4 with and without publication, missing and contradictory evidence, changed report content, fabricated audits, and exact freeze versus one microsecond after. |

## Architectural decisions and limits

- The registered plan binds the exact roster, schedule, target, geography,
  and timing constraints. The independent receipt binds the evidence mode. The panel digest
  and recomputed audits constrain membership, exclusions and coverage.
- All timestamp comparisons use UTC with aware input. Actual issue and
  availability times stay separate from simulated replay timing. Snapshot
  consistency applies to repeated immutable IDs across roles and folds, while
  geography remains part of the evaluation case.
- The structural archive, authenticated source evidence, verification result and
  scoring eligibility are distinct. Publication and panel fields may be absent
  in an archive. A populated value must match the trusted context. Verification
  checks the exact vintage and cutoff and leaves the archived shape and request
  digest intact. Materialization with additional evidence creates a distinct
  report, which requires separate verification.
- `VerifiedReport.matches` binds normalized manifest content. Keep an
  independently recorded file checksum and the original bytes if byte-level
  archival provenance matters, particularly for v3 migration. The caller is
  responsible for authenticating external records and re-verifying if those
  records change. There is no automatic registry or archival trust provider.
- PR #34 expects explicit versioned contracts, a panel, forecast archives,
  baselines and outcome observations. The future adapter needs authenticated
  inputs, exact geography and window joins, completeness and maturity checks,
  registered metrics and uncertainty, and provenance review before scoring.
  The synthetic fixtures and illustrative case studies provide no performance
  estimates or evidence of empirical forecasting skill.

## Validation evidence

| Exact repair revision | Local results | Remote results |
| --- | --- | --- |
| `3d537b3…` | 272 passed on each of Python 3.11.16 and 3.12.14 with PostgreSQL 16. Historical suite 74 passed. | [CI #176](https://github.com/bur5/geointel/actions/runs/45260558040) succeeded in both Python jobs and PostgreSQL integration. |
| `8743b40…` | 279 passed on each Python version with PostgreSQL 16. Historical suite 81 passed. Dedicated PostgreSQL suite 7 passed. | [CI #182](https://github.com/bur5/geointel/actions/runs/45297719188) succeeded in both Python jobs and PostgreSQL integration. |
| `44f405b…` | 300 passed on each Python version with PostgreSQL 16. Historical suite 102 passed, including a clean re-run during handover. Dedicated PostgreSQL suite 7 passed. | [CI #191](https://github.com/bur5/geointel/actions/runs/45301216973) succeeded in both Python jobs and PostgreSQL integration. The job results were rechecked for this handover. |

The repair's local matrix also passed Ruff lint and format, strict scoped mypy,
Git diff checks, and SQLite and PostgreSQL Alembic upgrades through `0008 (head)`.
Local pytest emitted one Starlette TestClient deprecation warning per invocation.
The 254-pass figure in the original request was a historical reference, not a
newly observed test result at handover.

## Reproduce on a fresh machine

Fetch and verify exact revisions from a clean clone. Put scratch worktrees and
disposable databases outside the source checkout.

```sh
git fetch origin refs/pull/45/head
test "$(git rev-parse FETCH_HEAD)" = 44f405b43514f4032f3f5a6d7ba9665bd81d7ffd
git worktree add --detach ../geointel-validation-45 FETCH_HEAD
cd ../geointel-validation-45
```

Use a separate virtual environment for both Python 3.11 and 3.12, activate it,
and install the project and test dependencies in each.

```sh
python -m pip install -e '.[dev]' mypy
ruff check .
ruff format --check .
python -m mypy --strict src/geointel/historical_validation
git diff --check HEAD^ HEAD
python -m pytest -o addopts= -q tests/test_historical_validation.py
```

Provision a disposable local PostgreSQL 16 database using the repository's
CI service recipe. Set `POSTGRES_TEST_URL` privately to its SQLAlchemy URL.
Run the migration and integration check. Repeat the full suite in both Python
environments with this URL configured.

```sh
DATABASE_URL="$POSTGRES_TEST_URL" alembic upgrade head
DATABASE_URL="$POSTGRES_TEST_URL" alembic current
python -m pytest -o addopts= -q tests/test_postgres_integration.py
python -m pytest -o addopts= -q
sqlite_dir="$(mktemp -d)"
DATABASE_URL="sqlite:///$sqlite_dir/validation.db" alembic upgrade head
DATABASE_URL="sqlite:///$sqlite_dir/validation.db" alembic current
```

See [main CI](https://github.com/bur5/geointel/blob/aaf887030e39a0960323096a7075be783aa97bdf/.github/workflows/ci.yml)
for optional smoke and service setup details.

### Preserved synthetic probes

Probe sources are preserved verbatim as text for historical reproduction.
Set `HANDOVER_PROBES` to the absolute path of this document's
`historical-validation` directory. Run from the target revision's checkout
with its dependencies installed and `PYTHONPATH=src`. These are local
synthetic diagnostics.

| Probe command | Compare | Expected observation |
| --- | --- | --- |
| `PYTHONPATH=src python "$HANDOVER_PROBES/baseline-check.py.txt"` | `3516810…` vs `3d537b3…` | The original accepts all four reported cases. The repair rejects the two v4 verification claims and both timestamp contradictions. Use the current regression suite for migrated v3 behavior. |
| `PYTHONPATH=src python "$HANDOVER_PROBES/deferred-probe.py.txt"` | `8743b40…` vs `44f405b…` | A saved report without publication triggers the digest mismatch at the former revision and verifies at the latter. A materialized report verifies on both. |
| `PYTHONPATH=src python "$HANDOVER_PROBES/digests.py.txt"` | `3516810…` vs `3d537b3…` | Identical plan, panel, and request digests, in that order. See [captured values](historical-validation/canonical-digests.txt). |

The checked-in v3 fixtures were produced by the `3516810…` builder using the
synthetic request, receipt and panel. The materialized variant sets availability
to the outcome freeze and uses the synthetic source reference
`synthetic:publisher:release`. The deferred variant omits the publication.
These file SHA-256 values are checksums of the original JSON bytes.

| Fixture under `tests/fixtures/` on PR #45 | File SHA-256 |
| --- | --- |
| `synthetic_benchmark_report_v3.json` | `03a7e83561d1eae2b834bffcd66bde316dab511501c3ba36fb152e966f44af9a` |
| `synthetic_benchmark_report_v3_deferred_publication.json` | `eff34b073b115412afb0e9cb9f17dd16b9b1c15f91307d1229711f10290ba078` |
