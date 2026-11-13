# Advisory pull-request evidence manifest

## Scope and authority

This is an isolated R3 protected-policy-related proposal for Owner review, based
on `main` a43ece92adc9c2bdd8652b740b12bdff9623aeee. The target governance is
[PR #25 at 3ff424d](https://github.com/bur5/geointel/tree/3ff424d086d0577f57c05584af2f0c493c6bd452),
not yet merged. Existing security and scientific requirements remain unchanged.
This feature is an observation tool, not an independent AI Reviewer or a gate.
It never approves a PR, labels it merge-ready, merges, deploys, comments, selects
new mandatory CI gates, changes branch protection, or modifies PR #24/#25.
No AI, paid API, new service, repository, account, secret or recurring job is used.

The [workflow](../.github/workflows/pr-evidence.yml) runs on PR open, synchronize,
reopen and ready-for-review events, including draft PRs. It has only `actions`,
`checks`, `contents` and `pull-requests` read permissions; all unspecified
GITHUB_TOKEN permissions are none. Artifact upload uses the standard Actions
artifact runtime capability, not repository write permissions. No custom secrets
are read. No checkout, package installation, local PR script, PR application code,
PR body/title, shell interpolation or `pull_request_target` is used. Only the
inline collector and two immutable-SHA-pinned official Actions execute. Pins were
resolved through GitHub's tag-ref API when preparing this proposal.

The workflow definition itself is PR-author-controlled in a PR run. Read-only
permissions and avoiding repository execution reduce exposure but do not attest
collector integrity. A malicious edit can forge an artifact; a digest proves
artifact identity, not truth. Always inspect the exact workflow revision and
Actions run provenance independently. Never promote this artifact or a green
workflow badge to a trusted gate without separately authorized enforcement.

## Collection and provenance

The collector performs only authenticated GitHub REST GETs. It validates the
repository ID/name and PR event, then reads live PR refs before and after
collection. Head/base changes, a closed/retargeted PR, API errors or uncertainty
make the snapshot incomplete. The event merge SHA is recorded but is **not**
claimed to be the actual checkout used by CI. The producing workflow ref/SHA,
run ID/attempt, actor and UTC start/end timestamps are recorded.

The fixed observation inventory mirrors the existing CI, without changing it:

- Workflow ID `363226887`, path `.github/workflows/ci.yml`, event `pull_request`.
- Jobs `test (3.11)`, `test (3.12)`, `postgres-integration`.
- Existing CI workflow blob `7418c8175a5f398351de27338d0006fb0795f369` must match
  at both event head and base. A changed baseline produces unknown evidence;
  updating it requires separate protected-policy review and Owner authorization.

It selects the newest matching PR CI run by run ID for the head, validates its
repository/workflow identity and PR head/base association, and fetches jobs for
that exact run attempt. It rechecks run attempt/status/conclusion at the end.
Each expected job must be unique and match run ID/attempt/head. Its check-run URL
must point to this repository's GitHub API; the returned check must match ID,
name, SHA, status/conclusion and the GitHub Actions App ID `15368`/slug
`github-actions`. Commit status contexts are deliberately ignored: a same-named
status or another App cannot substitute for the selected Actions job.

These are independently performed **metadata comparisons against fixed expected
values**, not independently executed tests or cryptographic attestations. Job
and step execution/conclusions, PR association and base metadata remain observed
GitHub assertions. Test semantics, coverage, source correctness, actual historical
checkout/integration, calibration/scientific validity, independent review, Owner
authorization and merge-time ref safety are not verified. Modifications to tests,
dependencies or application code can affect test validity even if CI YAML is
unchanged; the blob comparison does not solve that problem.

## Snapshot timing and failure behavior

There is one snapshot, no polling and no automatic CI-triggered rerun. The
workflow never waits for its own result, modifies CI, or creates a dependency in
CI. Missing or still-running CI is normal for the first PR event and is reported
as incomplete. After CI finishes, an authorized operator can use GitHub's normal
**Re-run jobs** for the evidence workflow only. A rerun uses its original event:
if head or base changed, it remains stale and cannot certify the newer candidate.
A fresh PR event is needed for a new candidate. Moving only `main` does not
necessarily emit a PR synchronize event; existing artifacts never auto-refresh.
Do not push empty commits or restart CI automatically to hide these limitations.

Each list endpoint is capped at three pages of 100 items; exhaustion, truncated
or malformed pagination fails closed. The full path makes at most 15 REST GETs,
with github-script API retries disabled, and has a five-minute job timeout.
Concurrency cancels older evidence runs for the same PR; cancellation may prevent
an artifact. API error text, headers and response bodies are never persisted.
Failures are recorded as fixed reason codes. Missing/incomplete evidence causes
a nonzero advisory job result after writing the JSON; upload runs with `always()`.
Platform startup, hard cancellation or upload failure can leave no artifact;
absence is unavailable evidence, never success.

## JSON schema and interpretation

[pr-evidence.schema.json](pr-evidence.schema.json) is a JSON Schema 2020-12 contract
for `geointel-pr-evidence-v1`. Fields are allowlisted; no approval/merge-ready
field exists. The schema is validated locally against generated fixture reports;
it is not a separately trusted validator in GitHub Actions.

| Field | Meaning |
| --- | --- |
| `schema_version`, `advisory` | Versioned contract and constant `true` advisory marker. |
| `repository`, `pr_number`, `candidate` | PR identity, event head repository/SHA, base branch/SHA and event merge SHA. |
| `provenance` | Producer workflow/run/attempt/actor, collection times, API origin and pinned CI inventory. |
| `observed_refs` | Live head/base observations before/after collection, or null if unavailable. |
| `ci_run` | Selected CI run identity, status, conclusion and timestamps; null if unavailable. |
| `checks` | Exactly three named job observations, with raw statuses/conclusions, job/check/App IDs, timestamps and step states. Missing source yields null evidence. |
| `independently_verified` | Metadata comparisons completed by the collector; never a formal independent review. |
| `observed_only`, `not_verified` | Explicit trust/coverage limitations. |
| `issues` | Fixed reason codes; a job-name suffix identifies the affected expected check. |
| `evidence_complete` | True only for a consistent snapshot with all inventory jobs/steps successful, trusted metadata comparisons and no issues. Does not mean approval or verified test validity. |
| `observation_state` | Aggregate observation, separate from authorization. |

States are `success`, `failure`, `pending`, `skipped`, `unknown`. Raw API values
are retained separately. Queued/in-progress/waiting/requested checks are pending;
failure/cancelled/timed-out/action-required/startup-failure/stale conclusions are
failure. Skipped is never success. Neutral or unrecognized states are unknown.
A job claiming success with skipped/missing/incomplete steps is skipped/unknown.
Aggregate precedence is failure, unknown, pending, skipped, then success only if
`evidence_complete`; otherwise unknown. Thus a known failure may coexist with
other missing evidence; always inspect completeness and issues as well.

Artifact names include producing run ID and attempt. The one JSON file has a
one-day retention request to bound storage. Downloaders must verify repository,
run/attempt, workflow revision, candidate and artifact provenance through GitHub;
never trust the artifact filename or its self-asserted fields alone. Expiration
requires regeneration, not treating a missing report as passed.

## Validation and follow-up

Run the dependency-free deterministic collector tests from the repository root:

```sh
node --test tools/test_pr_evidence.cjs
```

The tests execute the actual inline collector with mocked GET-only APIs, including
missing/duplicate jobs, SHA mismatch, stale/moving base/head, skipped jobs/steps,
pending CI, failure/neutral states, spoofed status/App/URL, changed CI baseline,
API denial, bounded pagination, new run attempt, missing provenance and timestamps.
They do not contact GitHub, databases or providers. Existing Python CI is unchanged;
these Node tests are currently a local verification command, not a new CI gate.

Before relying even operationally on the artifact, verify on this draft PR:

1. Fresh PR run emits pending/unknown while CI is incomplete; rerun only evidence
   after CI and inspect its artifact against live API refs/jobs/App metadata.
2. Compare every emitted JSON field with the schema; verify raw statuses, failed
   and skipped checks, denied API access and cancellation all fail closed.
3. Exercise head/base movement and run-attempt races on synthetic fixtures first;
   do not alter unrelated PRs or weaken real CI to manufacture failures.
4. Confirm token permissions, no checkout/secrets/comments/AI calls, and artifact
   upload/retention on actual GitHub runners. Test fork behavior separately if an
   authorized fork ever exists; do not create one for this milestone.
5. Verify workflow pin provenance, actual step execution, artifact digest and
   storage/compute allowance. Account for both existing push/PR CI and this job.

A real GitHub Actions/artifact run cannot be reproduced by local mocks. Current
GitHub Free private-repository protection limits and future independent-review
identity/merge atomicity remain unresolved. A hosted PR job can run without a
laptop, but provides no persistent Manager, scheduler or independent AI service.
Actions private-repository compute and artifact storage consume existing shared
allowances; the current balance and overage settings must be checked by the Owner.
No paid fallback or increased spending is authorized. If quota is unavailable,
stop; do not buy credits, enable billing or use a laptop runner as a hidden cloud
substitute. Later technical enforcement, auto-refresh, durable audit retention,
trusted baseline isolation and reviewer integration require separate proposals.
