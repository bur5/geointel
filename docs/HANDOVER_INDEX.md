# Unified handover index — 2026-11-23

All implementation work remains on its original refs. This index is a navigation layer, not a merged release. The four agents reported no unpublished authored implementation after preservation; inaccessible workspaces, original reviewer transcripts and external service configuration are not guaranteed preserved.

## Primary sources (immutable revisions)
- [Governance handover](https://github.com/bur5/geointel/blob/41ece80b8514eb7765cde20aa41032f93a9f3aed/docs/handover/README.md) — branch docs/geointel-codex-handover; includes [backlog index](https://github.com/bur5/geointel/blob/41ece80b8514eb7765cde20aa41032f93a9f3aed/docs/handover/open-prs.md), ref inventory, enforcement assessment and unapproved interim proposal.
- [Independent verifier experiment](https://github.com/bur5/geointel/tree/f5c408235ea83024e722a14ee4b9500604c3caf5/experiments/independent-ci-verifier) — experiment/geointel-independent-ci-verifier; simulated enforcement only.
- [Data Quality and Historical Profiles](https://github.com/bur5/geointel/blob/2c8c634bfd4b138bd51b8b80c94a28dcd90bcc19/docs/handover/geointel/README.md) — docs/geointel-codex-handover-3245d10; includes intermediate patches and validation evidence.
- [Historical Validation](https://github.com/bur5/geointel/blob/92c2864d1464c29ff7d4f3edd4880b37286928ec/docs/handover/HISTORICAL_VALIDATION.md) — docs/geointel-development-handover-44f405b; [23-PR inventory](https://github.com/bur5/geointel/blob/92c2864d1464c29ff7d4f3edd4880b37286928ec/docs/handover/OPEN_PULL_REQUESTS.md), synthetic reproduction probes.
- [Early Warning](https://github.com/bur5/geointel/blob/7edd02e6cd5bf8ced30551352e42e2ad31e56291/docs/handover/EARLY_WARNING_V1.md) — docs/handover-early-warning-v1-d69e9dfe; [review evidence](https://github.com/bur5/geointel/blob/7edd02e6cd5bf8ced30551352e42e2ad31e56291/docs/handover/EARLY_WARNING_V1_EVIDENCE.md).

## Verified current candidates
| Ref | SHA | State |
|---|---|---|
| main | aaf887030e39a0960323096a7075be783aa97bdf | baseline |
| [#25](https://github.com/bur5/geointel/pull/25) | c35871d407a534d8b4cb24af526c150f4c413709 | governance correction, independent review pending |
| [#32](https://github.com/bur5/geointel/pull/32) | 6cfba86c9b97796bf8f4eb0dbaad7e917a182a47 | draft CI, refresh after #25 |
| [#45](https://github.com/bur5/geointel/pull/45) | 44f405b43514f4032f3f5a6d7ba9665bd81d7ffd | draft, deferred publication repair, fresh review pending |
| [#46](https://github.com/bur5/geointel/pull/46) | 3245d1033117d03239e6a9a34d35ce0819320886 | draft, fresh review pending |
| [#47](https://github.com/bur5/geointel/pull/47) | d69e9dfe8f2aa9641dac9ba20cf93a85db5e81a9 | draft, fresh review pending |

## Architecture and backlog
Existing provider ingestion (ACLED, VIEWS, CAST, UCDP), evidence and forecast records, analysis, red-team, knowledge retrieval, persistence and monitoring form the baseline. Proposed branches extend it: #24/#33/#46 historical profiles and coverage; #34/#44/#45 scoring and historical validation; #35/#37/#47 early warning; #36 scenarios; #38 actor network; #39 briefings; #40 timeline; #41 search; #42 dashboard API; #43 frontend; #25–29/#32 governance and advisory manager tooling. Use the full pinned PR inventories for other branches and exact dependency details. Do not assume proposed modules are integrated.

## Recommended sequence (not authorization)
1. Read-only onboarding, reconcile live refs with archived inventory, verify review records and reproduce blockers.
2. Resolve governance #25/#32 and independent enforcement feasibility; no merge until all applicable gates are demonstrated and Owner authorizes exact candidate. Main protection was previously absent; recheck with authorized visibility.
3. Independently review #45/#46/#47 exact heads; reconcile superseded component PRs #44, #24/#33, #35/#37 without duplicating changes. #46 first legacy-to-v1 baseline suppression is an Owner tradeoff. #45 scoring remains unsupported until authenticated archive and outcome completeness; #34 needs separate integration. #47 requires approved thresholds, feed mappings, exact-query receipt issuer and point-in-time revision reader.
4. Plan integration of scenarios, search, actor network, timeline, briefings, dashboard and frontend after contracts are reconciled. No live predictive performance claims from synthetic tests.
5. Before any operational pilot, address private access/authentication, environment separation, secrets, backup/restore, migrations, scheduler idempotency, source freshness and notification authorization. Production remains HOLD.

## Owner decisions
Reviewer designation and authenticated approval channel; enforcement design and budget; overlap/integration sequence; historical baseline tradeoff; scoring protocol and archive access; early-warning thresholds and mapping; separate authorization for implementation, unattended work, deployment and public release. No interim exception is approved. Never commit API keys or restricted datasets.

## Validation and gaps
Agent reports preserve exact commands and results; candidate CI is advisory. #45 latest report records 102 focused tests and three green CI jobs; #46 reports 249 tests per Python version; #47 reports 231 per version and 52 focused hosted PostgreSQL tests. These are reported results, not a fresh independent run by the handover coordinator. Original off-platform reviews and inaccessible workspaces remain gaps. Do not claim empirical forecast calibration or production readiness.
