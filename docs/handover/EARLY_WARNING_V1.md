# GeoIntel Agent 4 handover for Claude Code

## Resume here

GeoIntel's canonical Early Warning v1 implementation is in [draft PR #47][47],
branch `review/early-warning-v1-2972262dd795`, at
`d69e9dfe8f2aa9641dac9ba20cf93a85db5e81a9`. This is the corrected advisory implementation
with passing fixture-based validation. Fresh independent review and Owner decisions
remain pending. Nothing in this handover grants authority to merge, deploy, schedule,
notify, or change repository settings. Follow [repository security and developer
permissions][security] and [intelligence agent rules][rules].

This documentation branch is based on the audited `main` tip
`aaf887030e39a0960323096a7075be783aa97bdf`. To work with the implementation, check out
the separate review branch. The [architecture and contract documentation][contract] lives
with that implementation. [Validation and reproduction](EARLY_WARNING_V1_EVIDENCE.md)
records exact commands, results and review regressions.

```bash
git fetch origin main refs/heads/review/early-warning-v1-2972262dd795
git rev-parse FETCH_HEAD
git show -s --format='%H%n%P%n%s' d69e9dfe8f2aa9641dac9ba20cf93a85db5e81a9
```

The last fetched ref above should resolve to the pinned review SHA for reproduction.
If it has advanced, inspect the intervening commits and use the pinned SHA to reproduce
these results. Current branch state takes precedence for future development.

## Implementation and decisions

- The original implementation commit, `2972262dd7955328c2f9f0b96d99f1394685f855`,
  directly descends from the audited `main`. It uses PR #35's typed evaluator and
  state model, with selected provenance, alignment and recovery safeguards from PR #37.
  The follow-up `d69e9dfe8f2aa9641dac9ba20cf93a85db5e81a9` directly descends from it
  and addresses the requested independent-review changes. Both commits are GitHub-reachable
  through the same PR #47 branch. They are stages of the same implementation.
- `src/geointel/early_warning.py` exposes the advisory evaluator. It uses explicit
  UTC evaluation and revision-cutoff days, canonical feed ordering, pinned model versions
  and target mappings, per-slot diagnostics, and held severity for missing data. Two
  distinct consecutive complete periods with the same lower candidate are required to
  downgrade. Only upward live transitions emit deterministic IDs.
- Reviewed, versioned activity mappings bind an exact provider and event filter to a
  common conflict target. Unconfigured feeds cannot contribute to CRITICAL. Verified
  event counts require an archived attestation bound to the exact query and receipt.
  The receipt ID binds the collection ID, provider, geography, filter and both window
  boundaries. Partial, stale, ambiguous, incomplete and unsupported historical or
  media inputs provide no verified count.
- `early_warning_inputs.py` adapts existing persisted records without mutation.
  GEOINTEL's four completed assessments, optional probability bounds, confidence,
  unknowns and Red Team output remain contextual. No midpoint or synthetic forecast
  probability is derived from an assessment. CAST remains in its native units.
  Only explicitly comparable external probability fractions enter numeric rules.
  VIEWS and the evaluator reject Boolean predictions before coercion.
- `early_warning_store.py` appends occurrence-keyed history and advances a checkpoint
  within one PostgreSQL transaction. It locks the stream checkpoint, returns the
  original snapshot on exact retry, uses a savepoint on failure and enforces unique
  upward transition IDs. Replay has a separate namespace and emits no live transition
  IDs. Migration `0009_early_warning` adds the two tables after `0008`. The
  operational monitoring service remains responsible for existing alert decisions.
- Numeric defaults carry forward PR #35 as a proposed evaluation profile. The threshold
  comparison with PR #37 is in the [pinned contract][contract]. A passing test suite
  establishes rule behavior on fixtures. Operational calibration remains open.

## Published refs and overlap

All listed PRs were open at audit time. These are observations of remote state, not
instructions to combine, close or replace work. Draft status is noted where observed.

| PR | Branch and exact audited head | Relationship |
| --- | --- | --- |
| [#47][47] (draft) | `review/early-warning-v1-2972262dd795` · `d69e9dfe8f2aa9641dac9ba20cf93a85db5e81a9` | Canonical Agent 4 review branch |
| [#35][35] (draft) | `codex/early-warning-v1` · `d10c93ede23ac402c31288ad9e6fbaab3ad9cb16` | Evaluator architecture and proposed threshold baseline |
| [#37][37] (draft) | `codex/geointel-early-warning-advisory-aaf8870` · `639d7e25ef0a1df41f111e8b25e8452c9a082759` | Input, alignment and same-candidate recovery safeguards. Its interval-midpoint proposal was excluded |
| [#24][24] | `codex/geointel-v0.1.8-historical-conflict-profile` · `d296ee720a45753ef4c1cf49fb23a77120a71303` | Historical context and taxonomy. Recheck target mappings if adopted |
| [#33][33] (draft) | `codex/data-quality-v1` · `df34d1bdd4f0edf0e30012bd67f1c669b77989f8` | Collection coverage and record eligibility proposal |
| [#46][46] (draft) | `review/dq-historical-b7956e594e9c` · `3245d1033117d03239e6a9a34d35ce0819320886` | Integrated data quality and historical profiles. The earlier recorded head `b7956e594e9c609aa4a93e45ff6fc55ff6dcad4b` is an ancestor. Recheck pipeline, monitoring and coverage contracts at the current head before writing an adapter |
| [#42][42] (draft) | `codex/dashboard-api-v1` · `1dca5a12573191670d8a2a778112eaab7cffe4d2` | Potential future advisory read API overlap |
| [#43][43] (draft) | `codex/geointel-frontend-v0.1` · `5ebbf6718a3e8b6be7b433bca65152d3ce3131fb` | Potential future presentation overlap |
| [#44][44] | `codex/historical-validation-foundation` · `3516810c74763a4c21d2c858969b24970723cf3f` | Related historical validation protocol. Assess suitability for offline evaluation |
| [#45][45] (draft) | `review/pr44-integrity-3d537b31-20261123` · `44f405b43514f4032f3f5a6d7ba9665bd81d7ffd` | PR #44 integrity repair. Review before relying on its protocol |

PR #47 builds on `main`. PRs #35 and #37 are design inputs, and the other open
PRs listed here are integration or review context. The receipt adapter should
consume individual verified coverage entries and record eligibility if that
contract lands. A broad window, complete status or empty result cannot by itself
prove completeness for a narrower filter and window.

## Unfinished work, known issues and Owner decisions

| Area | State and decision needed |
| --- | --- |
| Coverage producer and source roster | No operational attestation producer or approved activity mapping registry ships with PR #47. The code checks consistency and the exact binding. Trust in the attestation comes from a reviewed collector and immutable audit archive. Approve providers, geography, event filters, model versions and mapping owners. |
| Revision reader | Implement an approved point-in-time selector and archive the exact chosen revision IDs. Current cutoffs operate through end of day UTC. Competing visible versions are ambiguous. An intraday feed requires a separate design. |
| Legacy VIEWS payloads | When original adapter provenance is present, the persisted adapter rejects coerced Boolean predictions. A stored numeric value whose original type was lost cannot be classified from the number alone. Approve provenance and exclusion criteria for any historical replay. |
| Thresholds and calibration | Compare the PR #35 and #37 profiles on time-ordered, reviewable evidence. Approve thresholds, cadence, false-positive and lead-time criteria, and treatment of correlated feeds. Weekly slots may miss monthly model releases. |
| Schema and roles | Migration and least-privilege behavior are tested on disposable PostgreSQL. Production rollout, migration sequencing, backups, dedicated role provisioning and rollback policy require administrator and Owner review. Downgrade drops advisory history. Repository-wide Alembic metadata drift predates this implementation. |
| Presentation and operations | No scheduler, production API, UI, alert routing, or operational activation ships here. Retain missingness, provenance and uncertainty in any proposed consumer. Preserve monitoring ownership of alert materiality and resolution. |
| Independent approval | The corrections are ready for fresh review. The request described REQUEST_CHANGES and supplied reproduced findings. The GitHub review and inline-thread endpoints returned no records at audit time, so verbatim reviewer artifacts and authorship could not be verified. See the findings reconstruction in the evidence document. |

## Recommended sequence

1. Verify PR #47's current head and request fresh independent review through the
   established approval process. Review the eight regressions and compare the
   attestation trust boundary to the proposed collector.
2. Resolve the approved coverage and taxonomy dependency path. Review #46 at
   its latest head and use exact-filter evidence before generating any receipt.
3. Design the immutable archive and revision reader. Exercise look-ahead,
   truncated or ambiguous windows, source revisions, and replay isolation with
   offline fixtures before gathering any approved operational evidence.
4. Compare threshold profiles in an offline point-in-time evaluation. Bring the
   roster, mappings, policy and calibration results to the Owner. Keep execution
   and any advisory consumers behind the existing authorization boundary.

## Preservation inventory

| Local artifact | Audit finding and disposition |
| --- | --- |
| Original checkout, local `work` at `a43ece92adc9c2bdd8652b740b12bdff9623aeee` | Clean, already in remote `main` ancestry. An earlier reflog anchor `670639565c4f065c92a237e8134334cc17eefc9f` is also in that ancestry. |
| Early Warning review worktree at `d69e9dfe8f2aa9641dac9ba20cf93a85db5e81a9` | Clean, exact published PR #47 head. |
| Local `codex/canonical-early-warning-v1` and detached migration comparison worktree | Both point to `2972262dd7955328c2f9f0b96d99f1394685f855`, already in PR #47 ancestry. The detached worktree was a baseline comparison, with no unpublished changes. |
| Local integration input refs | PR #24, #33, #35, #37 and the older #46 input were all reachable via verified GitHub heads or ancestry. |
| Git status, stashes, reflogs and object check | No tracked modifications, nonignored untracked files, stashes, or unreachable objects were found in the shared repo audit. |
| Temporary edit scripts, request attachment and original PR draft text | Five scripts were sequential source/test rewrites that fed the two published commits. Their relevant changes are in Git history. The attachment's task context and the original PR draft's dependency notes are summarized in this handover and the review PR. Raw session materials were excluded. |
| Test logs, generated databases, interpreter environments and caches | Kept only reproducible commands and sanitized results. Disposable database files, raw logs, compiled caches and environments were excluded. |
| Other local directories and external artifacts | No additional project files in the accessible shared, scratch or library folders. No alternate agents' private workspaces, raw reviewer reports, operational archives, or credential stores were available for handover. Repository-owned peer work is linked through its existing refs. |

The handover publishes documentation only. No unpublished implementation required a
separate preservation branch.

[24]: https://github.com/bur5/geointel/pull/24
[33]: https://github.com/bur5/geointel/pull/33
[35]: https://github.com/bur5/geointel/pull/35
[37]: https://github.com/bur5/geointel/pull/37
[42]: https://github.com/bur5/geointel/pull/42
[43]: https://github.com/bur5/geointel/pull/43
[44]: https://github.com/bur5/geointel/pull/44
[45]: https://github.com/bur5/geointel/pull/45
[46]: https://github.com/bur5/geointel/pull/46
[47]: https://github.com/bur5/geointel/pull/47
[contract]: https://github.com/bur5/geointel/blob/d69e9dfe8f2aa9641dac9ba20cf93a85db5e81a9/docs/EARLY_WARNING.md
[rules]: https://github.com/bur5/geointel/blob/aaf887030e39a0960323096a7075be783aa97bdf/docs/AGENT_RULES.md
[security]: https://github.com/bur5/geointel/blob/aaf887030e39a0960323096a7075be783aa97bdf/docs/SECURITY.md
