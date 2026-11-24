# GEOINTEL development handover

This is a preservation record for the incoming Claude Code developer. It
covers the governance and CI assignment and indexes the wider visible backlog.
The two preservation branches are review artifacts. They grant no authority
to activate any feature, gate, unattended execution, merge, release, or deployment.

## Starting points

- Repository: private `bur5/geointel` (repository ID 1375475901).
- Live `main` at capture: `aaf887030e39a0960323096a7075be783aa97bdf`.
  This includes [#30](https://github.com/bur5/geointel/pull/30), the ACLED and
  PostgreSQL CI reproducibility change.
- [Open PR index](open-prs.md) records branch names and exact heads for the
  entire visible open backlog. [Remote ref snapshot](remote-refs.tsv) records
  49 branch heads, 47 PR heads and two current generated merge refs.
- [Experimental verifier](https://github.com/bur5/geointel/tree/f5c408235ea83024e722a14ee4b9500604c3caf5/experiments/independent-ci-verifier)
  is preserved at `f5c408235ea83024e722a14ee4b9500604c3caf5` on
  `experiment/geointel-independent-ci-verifier`. It uses synthetic data
  and does not create an integration or runtime dependency.
- [Zero-cost enforcement assessment](zero-cost-enforcement-assessment.md)
  records the evaluated architecture and operational gaps.
- [Baseline branch protection and interim proposal](protection-and-interim-proposal.md)
  is historical design material. The interim procedure is **unapproved**.
  Keep it outside the operative governance and merge path.

## Completed implementation and review history

### PR #25, governance milestone

Branch `codex/documentation-governance-milestone`, head
`c35871d407a534d8b4cb24af526c150f4c413709`. The four documents are
`GOVERNANCE.md`, `MANAGER.md`, `AGENTS.md` and `docs/SECURITY.md`.
They distinguish bounded implementation, additional unattended R1 authority,
manual merge, and deployment or release. They require binding independently
attributable review, trusted CI, effective protection and bypass coverage,
authenticated action-specific approvals, and the atomic exact head/base gate.

The Owner relayed REQUEST_CHANGES on
`80e381d997340f6be20cfd4c5601e618e78178bd`. The findings were to name the
atomicity blocker including this PR, apply protection to every merge, define
unattended starts/resumes/schedules/standing contracts/progression separately
from merge executor authority, bind deployment and release approval to the
immutable revision or artifact and destination, and correct candidate/CI
references. The published follow-up addresses each finding. Review, inline
comment and conversation endpoints were empty at handover, so this is a
summary of the relayed findings rather than an authenticated review record.
A fresh binding review for the published candidate remains pending.

GitHub's generated integration ref was
`ca3b2fa3989d8b77dc399e65e3f85573fe9970f8` with the live main and head as
parents and tree `772a35719143a408657ab12849406a0bec1dc3ae`. The PR and CI
metadata reported the earlier base `a43ece92adc9c2bdd8652b740b12bdff9623aeee`.
Keep both observations in the evidence record. Successful CI alone cannot
resolve the provenance discrepancy or satisfy the merge gate.

### PR #32, CI hardening

Branch `codex/ci-trust-boundary-v1`, head
`6cfba86c9b97796bf8f4eb0dbaad7e917a182a47`. It is a draft. The candidate
pins Actions and the PostgreSQL image, sets minimal permissions, disables
checkout credential persistence, bounds job runtimes, and adds PostgreSQL
execution and aggregate success checks. Its CI and test inventory remain
candidate-influenced. The original aggregate is useful regression evidence.
It cannot publish an independently trusted verdict.

A local merge-tree check combining the published #25 and #32 heads completed
cleanly and preserved both security sections. Refresh #32 after #25 advances
main and repeat exact-pair review, approvals and trusted CI. The #32 PR body
still describes an earlier R1 authorization statement and earlier CI heads.
The published branch text and exact-head run below are the current references.
No binding review is recorded on GitHub for either candidate.

## Verification and reproducibility

| Evidence | Result | Scope |
| --- | --- | --- |
| [#25 CI #189](https://github.com/bur5/geointel/actions/runs/45300513606) | Attempt 1 completed successfully. Python 3.11, 3.12 and PostgreSQL jobs succeeded. | Advisory and associated with the published head. Run metadata reports the earlier base above. |
| [#32 CI #186](https://github.com/bur5/geointel/actions/runs/45298374023) | Attempt 1 completed successfully. Python 3.11, 3.12, PostgreSQL and CI required checks succeeded. | Advisory. Run metadata reports the published head and live main. |
| Local #25 documentation checks | File allowlist, authorization statements, Markdown fences, local links and whitespace passed. | Static documentation checks. |
| Local integration checks | `git merge-tree --write-tree <main> <pr25>` and `git merge-tree --write-tree <pr25> <pr32>` passed. | Tree composition only. |
| Independent CI verifier | All 12 standard-library tests were reproduced on Python 3.12.14. Original and reproduced evidence and a SHA-256 manifest accompany the code. | Synthetic evidence and simulated enforcement, including concurrent merge and stale attempts. |

From the experiment directory, run `sha256sum -c SHA256SUMS` and
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v`. For application validation,
use the exact candidate's `.github/workflows/ci.yml` as the command inventory.
For changes requiring the full suite, use both Python versions, Ruff lint and
format checks, pytest, and the dedicated integration suite with a disposable
PostgreSQL 16 service and Alembic migration. Verify that PostgreSQL tests
actually ran. Keep live provider credentials and production databases outside
development validation. This preservation task reran only the experimental tests.

## Dependencies and unfinished work

- #25 precedes #32. #26 is an advisory evidence manifest whose workflow
  baseline needs reconciliation when #32 changes the workflow. #28 is a
  read-only collector and #29 an advisory integration contract. Extend their
  schemas only after the trusted evidence contract is chosen. #27 is the
  offline planner and #31 the advisory risk classifier. None confers execution
  or merge authority.
- The independent verifier lacks live authentication, a trusted runner and
  publisher, durable attempts/revocation, and a final merge transaction. Its
  shared lock controls the simulation only. GitHub's ordinary merge API
  supports an expected head and exposes no expected-base parameter. No
  compliant atomic merge operation was demonstrated.
- GitHub reports main unprotected, visible ruleset 27878104 disabled and
  auto-merge off. Detailed classic protection returned 403 during the prior
  inspection. Account entitlement, effective permissions and bypass coverage,
  trusted publisher availability, and zero-incremental-cost capacity are
  unverified. Exact-identity App checks would still leave the merge transaction
  unresolved. Enterprise Cloud queue eligibility and semantics do not apply
  to this private personal repository as configured.
- Wider backlog context is from authors' published PR descriptions. #45
  patches #44's historical validation provenance and conflicting snapshot
  declarations. #34 supplies scoring context. #46 overlays #24 historical
  taxonomy on #33 Data Quality, with #30 through main. It reports 243 tests on
  both Python versions and 134 pre-existing strict mypy diagnostics. #47
  combines #35 evaluator architecture with selected #37 advisory safeguards
  and reports 222 tests. #33 coverage and #24 historical context remain
  potential dependencies. Operational receipt production, point-in-time
  revision selection and a migration remain open in #47. These reported
  results were not reproduced in this governance handover.
- #42 Dashboard API and #43 frontend are separate drafts. The visible
  `codex/rebuild-dashboard-pr42-pr43` branch is already remote. Establish
  integration status from that branch and the PRs before making changes.
  #36 and #38–41 remain draft feature candidates listed in the PR index.

## Owner decisions and resume order

1. Authenticate the Owner's task scope and designate an independent reviewer
   for the exact #25 candidate. Check the live head/base, review designation,
   branch permissions and effective protections again.
2. Decide whether to authorize a separately scoped independent evidence pilot
   using existing compute. Confirm account entitlements and budget. Authorize
   any settings, Apps or production access separately. Keep the interim
   proposal unapproved unless the Owner separately initiates a policy change.
3. Independently demonstrate a compliant atomic merge operation before
   declaring any merge eligible. Verify Owner-only merge authority, no
   bypasses, trustworthy latest-attempt evidence and fail-closed recovery.
4. After independently verified gates and exact-candidate Owner approval,
   #25 may enter the separately authorized manual merge path. Refresh #32
   against the actual resulting main and renew evidence and approvals.
5. Only then coordinate the advisory tooling contracts and overlapping product
   branches. Keep thresholds, scientific claims, unattended authority and
   deployment or public release decisions separately scoped and authorized.

## Workspace audit and preservation gaps

The original checkout `work` pointed at
`a43ece92adc9c2bdd8652b740b12bdff9623aeee`, an ancestor of main.
Two detached governance worktrees held the published #25 and #32 heads.
All three were clean, with no stashes. Compared all local refs and reflogs
against fetched GitHub branch and PR refs. The only local-only reachable
commits were older GitHub-generated merge snapshots for #25 and #32,
`ad65c8ff57fdaa8cc3f750d41a5bcf95876baa80` and
`e9509b25a11d7cc8e78ee0be395a38ea96132710`. Their first parent is the
captured main and their second parents are published
`ef41b7dad02056bd2bb54a4a8e95e47a9574666d` and
`07bb91254b8b4a5dd256a08263aeed8503f324f5`. The respective trees are
`a3296f422bfa917fe0bacae21e7e74a22d36c86e` and
`984162e4e58e75610c95baf91ecdcf886c6aa0`. Recreate the trees with
`git merge-tree --write-tree <first-parent> <second-parent>`.
No authored implementation exists solely in those synthetic snapshots.
The dangling current #25 synthetic snapshot was reachable through GitHub.

The local #25 patch was byte-identical to the diff of published
`80e381d997340f6be20cfd4c5601e618e78178bd`. The isolated #32 patch
was published as part of `6cfba86c9b97796bf8f4eb0dbaad7e917a182a47`,
with an additional paragraph documenting its dependency on #25.
The two local assessments and the unique verifier files are preserved here
and on the experiment branch. The duplicate archive and Python bytecode
were omitted. The original task attachment was distilled into this report.

No other checkout associated with this assignment was found in the accessible
workspace. Other agents' workspaces, private service configuration, restricted
datasets, credentials and any original external independent review record
were outside this audit's visibility or scope. No raw chat, private environment
files, credentials, provider data or build caches are part of either artifact.
