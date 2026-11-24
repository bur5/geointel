# GEOINTEL zero-incremental-cost enforcement assessment

Scope is the private personal repository bur5/geointel, repository ID
1375475901. This assessment is read-only. The separate interim proposal
has no approval and supplies no merge authority.

| Control | Available approach | Evidence and limitations |
| --- | --- | --- |
| Independent CI execution | Use an existing separately administered isolated runner and a policy revision the PR cannot change. Fetch the exact integration commit and verify its parent SHAs. Run the mandatory inventory with disposable services. Keep credentials and the protected test entry point outside candidate execution. | Feasible in principle with existing authorized compute. No existing independent runner, protected policy deployment, or available quota was verified. Candidate Actions runs are advisory. |
| Evidence provenance | Use a separately controlled signer or App with a protected test manifest. Record repository and PR, both refs, integration SHA, policy, run and attempt, and mandatory job IDs and conclusions. An App check can be required by expected source if active protection supports it. | The local test checks trusted-adapter inputs. No App or signature verification was exercised. A signature authenticates its issuer and content. The consumer still needs current state, revocation, and key custody. |
| Reviewer authentication | Use a designated human reviewer with an authenticated GitHub identity or separately approved signing identity. Record Owner designation, review scope and independence, both SHAs, and outcome. Keep Owner approval separately attributable. | GitHub records review identity and commit. Governance still needs to verify designation, independence, and the base binding. |
| Stale evidence and concurrent updates | Use a transactional attempt ledger. Register a new authoritative attempt before dispatch, reconcile against the current GitHub refs and workflow attempts, and invalidate previous eligibility. Fail closed on unknown state, incomplete pagination, retries, or ambiguous changes. | Simulated locally. GitHub webhooks and check updates are asynchronous. A local transaction does not share a commit boundary with the GitHub merge operation. |
| Exact head/base merge | Require the final platform operation to reject either mismatched SHA. The ordinary merge endpoint accepts the head SHA. Strict checks can constrain base freshness but do not bind the approved base SHA. | No demonstrated compliant final operation. Direct ref updates or pushes would bypass the required PR merge route. A local lock, expected-head API call, and post-merge verification cannot substitute for the required transaction. |
| Owner-only merging | Keep auto-merge disabled. Audit all collaborators, integrations, deploy keys, and alternate write paths. Organization branch push restrictions can narrow writers under eligible plans. | Auto-merge off is observed. No Owner-only merge boundary was demonstrated on this personal repository, and the full ACL was not observable. A procedural freeze does not satisfy the atomic gate. |
| Audit, recovery and revocation | Record signed, append-only verdicts and approvals in independently controlled durable storage. Record policy, identities, revocations, attempts, and source evidence. Reconcile after restart before resuming. On STOP or ambiguity, halt and invalidate eligibility, then require fresh verification and approvals. | Storage and authority separation need an approved owner and capacity. The prototype uses in-memory state. PR review history alone cannot prove current eligibility and can omit external decisions. |

An existing approved runner, protected policy store, signer, and audit store
could support independent advisory evidence with zero incremental spend.
No such deployed system was verified. Account entitlement and compute quota
were unavailable. Personal Pro is the minimum documented plan for protecting
a private personal repository, and paid protection alone does not establish
an exact-pair merge boundary.

Sources:
- https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request
- https://docs.github.com/en/rest/checks/runs
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
