# GEOINTEL branch protection and interim merge proposal

Status as of November 23, 2026: historical proposal preserved for Owner review. The current
policy requires an operation that rejects a mismatch on either approved ref.
The interim proposal requires a separate protected-policy amendment.

## Account and repository evidence

Repository ID 1375475901 is private and owned by a personal account.
GitHub reports main as unprotected and auto-merge as disabled. The sole
visible ruleset, 27878104, is disabled. It targets the default branch, has an
empty bypass list, and lists one required approval, stale-review dismissal,
latest-push approval, conversation resolution, strict check freshness, no
deletion or force push, and three Actions checks from App 15368. The connector
was denied the classic protection detail endpoint. Account billing and the
ability to activate the draft rules were not visible. The draft and its API
visibility establish existence only. The Owner must verify the exact plan and
feature availability in authenticated Billing and Settings.

| Tier | Enforcement for a private repository |
| --- | --- |
| Personal Free | Private PR review and Actions are available subject to account usage limits. Private branch protection and active branch rulesets require a paid eligible plan. |
| Personal Pro | Private protected branches and repository branch rulesets. This is the minimum documented tier for the personal repository configuration below. |
| Organization Free | Team-based collaboration and access roles are useful. Private branch protection and active private branch rulesets still need an eligible paid plan. |
| Organization Team | Private branch protections, repository rulesets, team and admin separation, and organization branch push restrictions. These materially improve who can merge or update main if permissions are configured and tested. They do not add an expected-base input to the merge transaction. |
| Enterprise Cloud organization | Adds eligibility for private merge queues and organization ruleset required workflows. A queue validates a merge group and completes merges after admission. Neither entitlement by itself binds the Owner's separate approval to both refs in the platform transaction. |

GitHub plan overview: https://docs.github.com/en/get-started/learning-about-github/githubs-plans
Protected branches: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
Branch rulesets: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
Merge queue: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue

## Minimum branch protection to stage

Use a single active branch ruleset explicitly targeting refs/heads/main
on an eligible plan. Use the equivalent classic branch protection only if
needed and verify that it applies to admins and bypass-capable roles. Review
the disabled ruleset against the following settings before proposing activation.

| Setting | Proposed value |
| --- | --- |
| Enforcement and scope | Active on refs/heads/main. Keep the repository private. |
| Bypass | Empty. No admin, collaborator, or App bypass. In classic protection enable Do not allow bypassing the above settings. |
| Branch updates | Require changes through a pull request. Block force pushes and deletion. |
| Reviews | Require at least one approving review, dismiss stale approvals on changes affecting the review, require approval of the most recent reviewable push by someone other than its pusher, and require resolution of conversations. Preserve any stronger requirement, including the existing draft's additional approval for unattributed changes. |
| Advisory CI as baseline status checks | Require test (3.11), test (3.12), and postgres-integration from GitHub Actions (App 15368) if the contexts are still stable. Enable Require branches to be up to date before merging. These are regression checks that remain candidate-influenced. |
| Trusted evidence | Independently verify the exact candidate under protected policy. Only add an App check after separate authorization and a successful live pilot, selecting the expected App rather than Any source. |
| Automatic merging | Keep repository auto-merge disabled. Do not enable a queue or give an integration merge authority. |

GitHub can enforce the protected branch route, the configured count and
freshness of GitHub reviews, thread resolution, named check/source requirements
with strict up-to-date mode, and the configured restrictions on branch deletion,
force push and bypass. The repository administrator can still change settings.
Check freshness and review dismissal follow GitHub's rules about the diff,
merge base, and latest reviewable push. They do not cover every movement of the
live base. Required checks can accept success, skipped or neutral under GitHub
semantics. The three Actions checks remain candidate-influenced.

Reviewer independence and Owner designation, authenticated Owner merge approval,
the exact evidence tuple, success-only jobs and attempt supersession, and the
approved workflow/test inventory require independent controls. On the personal
repository, manual Owner-only merging is procedural if other collaborators have
write access. GitHub's documented push allowlist for protected branches requires
organization ownership and an eligible private-repository plan. The ordinary PR
merge API accepts an expected head SHA but exposes no expected-base SHA input.
Neither a last-second read nor an after-the-fact check closes that gap.

Merge endpoint: https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request

## Proposed interim amendment for explicit Owner decision

If adopted through a separately reviewed governance change, permit the Owner
alone to perform a listed, one-at-a-time PR merge during a defined time window.
The amendment substitutes supervision and post-merge detection for atomic
rejection of base or attempt drift. The Owner explicitly accepts that another
write or evidence change can occur between verification and merge. The
amendment retains trusted CI, independent review, and exact-pair approval and
must specify PRs in scope, start/end, reviewer, evidence source, and recovery.

1. Confirm active protections and no bypass. Pause concurrent merges,
   branch updates and reruns. Confirm there is no queued or automated writer.
   Stop if the Owner cannot account for all write paths. This pause is procedural.
2. Capture live repository ID, PR, head, base, and the integration commit with
   the expected parent SHAs. Obtain fresh independently controlled CI evidence
   for that integration commit, including policy revision, run and attempt,
   mandatory job identities and explicit success. Candidate CI alone cannot
   satisfy the trusted CI requirement. Stop if no approved independent source
   exists. This draft does not activate an App or provision a source.
3. Record binding independent approval and authenticated Owner approval for
   the exact pair and selected merge method. Use a merge commit for this
   proposal so its parents and tree can be compared to the approved candidate.
   Require a fresh review and approval following any observed head or base change.
4. The Owner immediately re-reads live head/base, effective protection and
   latest authoritative attempt. Abort on any discrepancy or ambiguity. Invoke
   the PR merge API manually with the expected head SHA and merge method
   merge. Do not retry an ambiguous response until repository state is known.
5. Inspect the resulting merge commit and confirm both approved parents and
   the tested tree. Record the result. On discrepancy, halt further merges
   and releases, preserve evidence, and escalate for an independently reviewed
   recovery. A post-merge check detects drift after the update has happened.
6. Let the amendment expire at the approved deadline or earlier at Owner STOP,
   control failure, or policy supersession. Resume the original atomic rule
   when the amendment expires. Production deployment and public release remain
   separate explicit decisions.

## Published references

The baseline and interim material above remains a proposal. The subsequent
governance corrections are recorded on PR #25 at
c35871d407a534d8b4cb24af526c150f4c413709 and PR #32 at
6cfba86c9b97796bf8f4eb0dbaad7e917a182a47. See the [handover](README.md)
for the latest evidence and the isolated experimental verifier.
