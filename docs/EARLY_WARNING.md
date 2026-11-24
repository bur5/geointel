# GEOINTEL Early Warning v1 integration decision

Use one advisory evaluator, `geointel.early_warning.evaluate`, on the architecture of PR
#35. It returns a typed snapshot and resumable checkpoint from explicit inputs. The
integration adopts PR #37's explicit target mapping, declared probability scale, per-slot
coverage, alignment of target dates across models in every slot, persisted-record adapters,
same-candidate recovery, and canonical feed ordering. Use
`early_warning_store.persist_evaluation` when the snapshot and checkpoint must be durable.

## Verified references

| Source | Commit | Relationship to integration |
| --- | --- | --- |
| [main](https://github.com/bur5/geointel/commit/aaf887030e39a0960323096a7075be783aa97bdf) | `aaf887030e39a0960323096a7075be783aa97bdf` | Exact reviewed base |
| [PR #35](https://github.com/bur5/geointel/pull/35) | `d10c93ede23ac402c31288ad9e6fbaab3ad9cb16` | Evaluator architecture and synthetic regression baseline |
| [PR #37](https://github.com/bur5/geointel/pull/37) | `639d7e25ef0a1df41f111e8b25e8452c9a082759` | Selected input and recovery safeguards |
| [PR #33](https://github.com/bur5/geointel/pull/33) | `df34d1bdd4f0edf0e30012bd67f1c669b77989f8` | Proposed collection coverage and eligibility |
| [PR #46](https://github.com/bur5/geointel/pull/46) | `b7956e594e9c609aa4a93e45ff6fc55ff6dcad4b` | Proposed integrated coverage, monitoring diagnostics and historical context |
| [PR #24](https://github.com/bur5/geointel/pull/24) | `d296ee720a45753ef4c1cf49fb23a77120a71303` | Proposed historical representation and taxonomy changes |

The heads of #35 and #37 both fork directly from the verified base. The inspected heads of
#24, #33 and #46 are outside the ancestry of that base. The branch uses existing Pydantic and
SQLAlchemy dependencies and is isolated from pipeline entry points, API routes, monitoring
and notifications.

## Source-to-target contract

| Source | Advisory destination | Admission and provenance |
| --- | --- | --- |
| External `ForecastSignal` | Probability observation for a configured feed | A reviewed `TargetMapping` binds provider, model, version, native target, geography unit and calendar-month horizon to a common conflict target. Require `aligned`, `unit="probability"` and `scale="0-1"`. The value must be finite and within the inclusive unit interval. Retain source record ID, issue and target dates and the mapping. Availability uses the latest issue, retrieval or persistence day. |
| Operational `Event` | Count observation for one provider, country and event type | Require explicit operational and alignment provenance matching the row, exact receipt membership, occurrence in the closed query window and availability by the receipt. De-duplicate by provider record ID within a window. A repeated identity across nonoverlapping slots makes the series unusable. |
| GEOINTEL `Forecast` from a completed run | Read-only contextual view | Preserve assessment and run IDs, conflict type, question, horizon, optional probability bounds, confidence, unknowns and Red Team output. Keep both bounds as supplied. The view supplies no scalar probability to the evaluator. The four-category forecast output and its existing immutable persistence contract remain in the normal analysis path. |
| CAST, annual GED, Candidate GED, historical records and delayed news | Existing context paths | CAST event counts retain their native units. Historical releases, provisional historical evidence and media reports are ineligible for operational receipts. |

The persisted adapters read ORM fields and explicit source metadata. The country adapters
resolve aliases through the repository's bounded, reviewed country mapping. Other geography
units require an exact configured identity. A scope pins the mapping for every expected
model and canonicalizes the feed and mapping order. Feed identifiers use their configured
provider-native spelling. Map provider aliases before constructing a scope. Each activity feed in the roster requires an `ActivityMapping` naming its exact provider and
event filter, canonical conflict target, mapping version and review reference. Every mapping in
a scope must share a single target. Only activity from that roster can corroborate a forecast
for CRITICAL. Use an approved mapping artifact as the source of these configuration values.
Changing a model version, mapping, feed roster, scope or thresholds creates a new stream.
The VIEWS payload, normalized signal and advisory observation boundaries reject Boolean
predictions before numeric coercion. Stored VIEWS forecasts are also checked when raw
adapter provenance is present.

Each scheduled slot is a fixed-width inclusive UTC date window. Forecasts sit in the slot
containing their issue date. The reviewed mapping derives full target months from that issue
date. Models must supply identical explicit target start and end dates within each slot.
Rolling slots may point at different target months as the issue month advances. Expiry is
checked for the latest forecast against the evaluation day. The current implementation
supports full calendar-month targets with a positive issue-month offset. Other target
calendar conventions require their own reviewed mapping.

## Coverage and provenance

A trusted collector should persist one immutable receipt per exact provider, canonical
country, event filter and UTC period. `OperationalReceipt` carries that scope, the receipt
ID, the operational classification, completion time, availability time, coverage status
and the distinct source identities for the exact filter. The receipt ID is derived from the
collection ID, provider, country, event filter and both window boundaries. A copied receipt
with any different binding is rejected. For a verified receipt,
completion must occur after the final UTC date in the window, and availability must be at
or after completion. The persisted adapter also checks record persistence against receipt
availability. Feed freshness is assessed relative to the newest structurally usable slot.

Issuance of `verified_complete` requires auditable success, exact query and verified
scopes, complete pagination, reconciled counts and no unresolved restrictions, rejections,
truncation, stale snapshot or ambiguous terminal page. An `OperationalAttestation` must name
the same exact query and an immutable audit reference, and affirm exhausted pagination, an
unrestricted query and reconciled counts. Archive the provider query and evidence for those
claims behind that reference. The evaluator validates the receipt binding, attestation and
source membership. The receipt issuer is responsible for
verifying the upstream audit and establishing the earliest actual availability. A verified
complete result with an empty source roster establishes zero returned events for that
provider and filter.

Partial, stale, truncated and ambiguous receipts produce no count. Unavailable records
stay outside the point-in-time snapshot. Every expected slot reports status and any
supplied observations that were available by the cutoff. Feed-level diagnostics cover
freshness, expiry, repeated identities and dated model alignment failures. Any required
input problem yields `INSUFFICIENT_DATA`, resets recovery and shows the held severity and
retained evidence.

## Threshold decision for Owner review

The checked-in defaults retain PR #35's numbers for regression and replay. Approve one
explicit policy before any operational use. The proposed evaluation profile is the PR #35
column, with same-candidate recovery and upward-only IDs. It preserves the existing
indicator baselines while the two profiles can be compared on the same point-in-time
archive. Threshold deltas use percentage points and boundary comparisons are inclusive.

| Rule | PR #35 and proposed evaluation profile | PR #37 |
| --- | --- | --- |
| Slot cadence and required history | Three consecutive 7-day observations | Four consecutive 7-day observations |
| Maximum latest slot age | 10 days plus target expiry check | 7 days, no comparable expiry gate |
| Forecast jump | 15 points | 15 points |
| Sustained forecast rise | 2.5 points each step and 10 total | 2 points each step and 12 total |
| Emerging risk | Baselines at most 10%, current at least 20% | Baselines at most 5%, current at least 12% |
| Model disagreement | 25-point spread or opposing changes of 15 points each | 25-point spread |
| Activity jump | At least 5 extra events and twice the prior count | Same |
| Sustained activity rise | At least 2 additional events per step and 5 overall | No separate rule |
| Recovery | Two consecutive lower readings in original #35 | Two consecutive readings of the same lower candidate |
| Transition IDs | Upward only | Downward into an elevated level also generated an ID |

`NORMAL` means the complete window met no qualifying rule. `WATCH` covers emerging risk
or model conflict. `WARNING` covers jumps and sustained change. `CRITICAL` requires
an activity jump plus a forecast jump or sustained forecast deterioration, with model
disagreement and opposing movement blocking promotion. Escalation takes effect immediately.
Two distinct consecutive complete slots with the same lower candidate are required before
downgrade. A gap, skipped slot or change of candidate breaks the recovery sequence. A
same-slot revision cannot add a recovery period. The monitoring service owns notification
materiality, deduplication and resolution. Advisory downgrades produce no resolution
action.

## Persistence, cutoffs and replay

- The PostgreSQL implementation uses a single history table and a checkpoint table,
  defined in `early_warning_store.metadata`. Alembic revision `0009_early_warning` creates
  the tables, composite primary keys, foreign key and unique nullable transition ID. Its
  downgrade removes both advisory tables and their contents. The migration is tested for
  clean install, downgrade to `0008`, and re-upgrade on a disposable database.
- A method-versioned hash identifies the canonical scope and threshold configuration. An
  occurrence is keyed by namespace, stream, scheduled period end, UTC evaluation date
  and explicit UTC revision cutoff. An exact retry returns the originally persisted
  snapshot. Revisions append history under a new key.
- The writer inserts the checkpoint identity if needed, locks that row and checks for an
  existing occurrence under PostgreSQL READ COMMITTED. History insertion and checkpoint
  advance share the caller's transaction. A savepoint also rolls back a failed call when
  the caller catches the exception. Commit before consuming the record. The history
  enforces unique deterministic upward IDs derived from stream, slot and destination level.
- Dates are inclusive through end of day UTC. The revision cutoff must be at or before
  `as_of`. Append new occurrences in nondecreasing period, evaluation day and cutoff
  order within each namespace and stream. Evidence can enter only once available by the
  cutoff. For same-day ordering, a future version needs time-of-day cutoffs and timestamped
  revision keys.
- Supply the immutable set of records visible at the cutoff. Identical observations
  collapse. Competing visible versions make the slot ambiguous. A point-in-time reader
  that resolves revisions should use an approved version-selection rule and archive the
  selected version IDs. When evidence arrives after the live checkpoint passes a slot,
  re-evaluate history in a fresh replay namespace. Backdated snapshots cannot advance the
  live checkpoint.
- Replay uses a caller-chosen replay ID and a separate checkpoint in the same history.
  Replay snapshots identify their mode and emit no transition IDs. The persistence path
  only writes advisory history and checkpoints.

## Integration dependencies

1. **PR #46 and PR #33 coverage.** If the versioned `CoverageDecision` lands, consume
   individual collection entries and per-record eligibility as inputs to the audit.
   A coverage status alone cannot certify an exact event-filter window.
   Certify only eligible operational event queries with verified exact provider, country,
   UTC dates and event filter. Require `complete_empty` or `complete_with_records`,
   and inspect verification, page termination, restrictions, rejections and record audit.
   A broad rolling query requires separately proven coverage for the narrower slot and
   filter. Supply a versioned receipt that retains the collection ID, completion and
   availability timestamps and exact matching provider record IDs. Legacy, missing or
   unverified coverage leaves the slot incomplete.
2. **PR #24 historical evidence.** If its profile and taxonomy are adopted, keep that
   projection on the contextual read path. Review forecast-category mappings against the
   updated taxonomy and rerun existing monitoring and four-category forecast regressions.
3. **Operational read path.** Approve the provider/model roster, activity mappings, target
   windows, exact event filters, source revision policy and receipt producer. Keep scheduling,
   API exposure and monitoring integration outside this patch.

### PostgreSQL runtime grants

Run the migration as the schema owner. Provision a dedicated, non-owner runtime login
through the existing database administration process. For the default PostgreSQL
`public` schema, the advisory writer needs these grants in its database. Substitute the
actual database, schema and role identifiers.

```sql
GRANT CONNECT ON DATABASE geointel TO geointel_advisory;
GRANT USAGE ON SCHEMA public TO geointel_advisory;
GRANT SELECT, INSERT ON public.early_warning_history TO geointel_advisory;
GRANT SELECT, INSERT, UPDATE ON public.early_warning_checkpoints TO geointel_advisory;
```

Checkpoint INSERT supports the first evaluation. UPDATE supports row locking and writes.
The test suite authenticates through separate non-owner PostgreSQL logins, exercises
concurrent retries and state recovery, and verifies history deletion is denied. Migration
DDL and production role provisioning remain administrator operations.

## Remaining risks and independent review

- Verify each provider's numeric semantics and target mapping with representative archived
  records. Forecast versions, geography changes and taxonomy changes can break
  comparability. A weekly cadence can leave regular gaps for monthly model releases.
- Audit filtered coverage receipts and archive completeness. Provider reporting backlogs,
  source restrictions, reclassifications and different IDs for the same real-world event
  can create false spikes or missed changes.
- Confirm the proposed policy using time-ordered archives. Measure coverage, alert burden,
  false positives, lead time and sensitivity across both threshold profiles. Event feeds
  and forecasts can share inputs, which weakens the interpretation of corroboration.
- Trace an exact retry, transaction rollback, late record and replay through the history
  and checkpoint. Check that competing revisions and incomplete readings remain visible
  and monitoring remains the owner of alert handling.
- Verify the reviewed branch base and confirm migration rollout, collector changes
  and threshold approval independently before wiring an operational entry point.

## Validation

Use a migrated disposable PostgreSQL 16 database. Run `pytest` with
`POSTGRES_TEST_URL`, `ruff check .`, `ruff format --check .`, and
`mypy --follow-imports=silent src/geointel/early_warning*.py`. The regression suite covers
rule boundaries, immediate escalation, opposing movement, outages, sparse slots, same-candidate
recovery, coverage and source identity, provider semantics, model alignment and expiry,
historical forecast immutability, existing monitoring and API behavior, concurrent retries,
transaction rollback and replay. These tests validate deterministic behavior with fixtures.

The PostgreSQL CI job runs the legacy integration suite and all advisory tests. Set
`POSTGRES_TEST_URL` to a disposable PostgreSQL 16 database with permissions to create
temporary schemas, databases and roles for the tests. The tests use separate runtime
logins with the grants above for advisory persistence.
