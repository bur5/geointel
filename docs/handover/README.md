# GeoIntel development handover

This snapshot was prepared on 2026-11-23 Pacific time for the transition from Codex to
Claude Code. The assigned workstream was Historical Validation. It includes a local
implementation audit, a repository-wide index of visible open PRs, and the evidence
needed to resume the Historical Validation review. Start with the repository's
[agent rules](../AGENT_RULES.md), [security guidance](../SECURITY.md), and the
owner's current governance instructions.

## Resume points

| Work | GitHub ref or branch | Verified commit |
| --- | --- | --- |
| Repository baseline | `main` | `aaf887030e39a0960323096a7075be783aa97bdf` |
| Historical validation foundation | `codex/historical-validation-foundation` | `3516810c74763a4c21d2c858969b24970723cf3f` |
| Historical Validation repair and follow-ups | `review/pr44-integrity-3d537b31-20261123` | `44f405b43514f4032f3f5a6d7ba9665bd81d7ffd` |
| This handover | `docs/geointel-development-handover-44f405b` | Resolve the branch tip on GitHub |

The repair is published as draft PR #45, stacked directly on PR #44. Its
merge base with `main` at audit time was the baseline shown above. Review
the repair alone with `git diff 3516810c74763a4c21d2c858969b24970723cf3f
44f405b43514f4032f3f5a6d7ba9665bd81d7ffd`. GitHub's draft comparison against
`main` also includes the inherited foundation commits. The documentation
branch is based on `main` and contains only handover material.
[PR #44](https://github.com/bur5/geointel/pull/44) · [PR #45](https://github.com/bur5/geointel/pull/45)

- [Historical Validation implementation history, findings, evidence, and commands](HISTORICAL_VALIDATION.md)
- [Open PR inventory with branch names and exact head SHAs](OPEN_PULL_REQUESTS.md)

## Local preservation audit

| Local item | Disposition |
| --- | --- |
| `geointel` worktree, branch `work` | Clean at `a43ece92adc9c2bdd8652b740b12bdff9623aeee` (merge of #23). This commit is an ancestor of remote `main`. |
| `pr44` worktree, branch `codex/pr44-integrity` | Clean at `44f405b43514f4032f3f5a6d7ba9665bd81d7ffd`. Remote PR #45 and its branch have the identical head. All intermediate commits are reachable through that head. |
| Ref, reflog and object inventory | Two source worktrees shared one Git object store. No other source checkout, tag, stash, inaccessible registered worktree, untracked source, or unreachable objects were found in the accessible workspace. The historical reflog commits were accounted for by GitHub branch ancestry. |
| Three PR #44 scratch source archives | Compared byte-for-byte with a fresh archive of `3516810…`, excluding Python bytecode directories. All three matched. Git recreates them from that commit. |
| Standalone experiment files | Three synthetic probes and the canonical digest output are preserved under [historical-validation](historical-validation/). The before and after digest output files were identical. |
| Scratch test databases, environments, and caches | Three disposable SQLite migration-check files, two virtual environments, the provisioned interpreter, and generated caches were excluded. The PostgreSQL containers were ephemeral and stopped. The runbook recreates the checks. |
| Original task brief, iterations, and independent review findings | Relevant technical requirements and findings are recorded in the Historical Validation handover. Raw conversation exports, reviewer identity, and private workspace metadata were excluded. |

No unpublished implementation or unfinished feature code was found in the
accessible local worktrees. The documentation branch preserves the local
experiment record. The open-PR index covers remote project context
visible to the repository connection, including workstreams whose local
workspaces were outside this assignment.

## Dependencies and overlaps

- **#44 and #45.** The foundation and repair share Historical Validation code
  and manifest contracts. The owner must decide how to land the repair with
  its foundation and which exact commit receives final independent acceptance.
- **#34.** The backtesting PR is the prospective scoring dependency. Its code
  and tests use separate paths. Joining its scoring inputs to #45's frozen
  audits, forecasts, baselines and outcomes remains integration work.
- **#24, #33 and #46.** Taxonomy and coverage are related contracts. #46 combines
  Historical Conflict Profiles with Data Quality and monitoring work. Its
  originally published integration commit `b7956e594e9c609aa4a93e45ff6fc55ff6dcad4b`
  is an ancestor of the current #46 head shown in the PR index. Verify the
  successor head's own test and review status before depending on it.
- **#35, #37 and #47.** These overlap on advisory Early Warning. #47 integrates
  the evaluator with selected input safeguards. Its original candidate
  `2972262dd7955328c2f9f0b96d99f1394685f855` is an ancestor of its current
  head. Advisory thresholds, trusted receipts, operational migrations, and
  any activation require owner decisions. Historical alert replay depends on
  a selected and independently reviewed advisory contract.
- **Governance and CI.** #25–#29 and #32 contain proposed governance, evidence,
  AI Manager or CI trust work. The observed `main` incorporates #30. Read the
  current repository rules and each proposed PR before applying its policies.
  The PR index captures other feature tracks for overlap checks.

## Owner decisions and next steps

1. Give the successor an authorized repository connection. Fetch PR #45 and
   verify its head against the table before making changes.
2. Request a fresh independent review at the exact PR #45 head. Reconcile
   reviewer reports outside GitHub with that commit and record their evidence.
3. Decide the merge sequence for #44 and #45 and how the foundation and repair
   should be reviewed together. Coordinate any cross-workstream decisions with
   the corresponding owners before taking a dependency.
4. If empirical evaluation is authorized, select authenticated archives, versioned
   outcome taxonomy, and a registered panel. Review a separate #34 adapter design
   for per-case eligibility, completeness, and uncertainty. The current benchmark
   package explicitly reports scoring as unsupported.
5. Ask owners of other Codex sessions to confirm that they have exported any
   unpublished workspaces, artifacts or private review reports. GitHub reachability
   confirms the published refs and says nothing about unshared local work elsewhere.

## Gaps and exclusions

No separate agent sessions or privately held reviewer transcripts were accessible
from this workspace. GitHub's review and inline-thread endpoints returned empty
lists for PR #45 during the audit. The two change-request rounds described in the
task history are preserved as findings and linked to the commits that addressed
them. Fresh independent acceptance for `44f405b…` was unavailable. Raw historical
terminal logs were not present as files. Their command results are recorded
alongside the reproducible checks and CI links. The handover contains synthetic
inputs only. It excludes credentials, keys, personal information, private
configuration, restricted datasets, service state and generated build artifacts.
