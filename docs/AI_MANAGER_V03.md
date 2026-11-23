# AI Manager v0.3 integration contract

The contract converts two trusted GitHub State Collector v0.2 captures into
short-lived, advisory Manager input. It preserves the full open PR inventory,
including draft and fork metadata, per-PR target branches, head and base SHAs,
CI and review observations, and request provenance. An empty inventory is
valid when both captures independently observed it. The module has no CLI,
credentials, network client, write path, scheduler, dispatcher, or merge path.

## Caller and trust boundaries

Call `prepare_manager_input(read_observation, collector_revision=..., clock=...)`
from trusted application code. Bind the reader to the exact reviewed collector
build and the clock to a trusted UTC source. The reader must perform a fresh
collection on each invocation, with caching and replay disabled, then return
the native snapshot as a Python dictionary. Supply the collector revision from
trusted deployment metadata. A matching revision string or transport field in
an uploaded report provides no producer authentication. There is no file or
request-body entry point. The bridge checks the v0.2 digest for integrity only.

| Data | Handling |
| --- | --- |
| Observed GitHub facts | PR identity, refs, CI and review metadata, and source records are retained. Ref names, account names and other external strings are inert data. |
| Untrusted content | PR titles and bodies, comments, review summaries, and the embedded v0.1 payload are excluded. Never use these to provide instructions or authority. |
| Manager recommendations | Advisory only. A recommendation and its stated risk tier confer no permissions. A trusted policy evaluator must independently determine any effective risk tier. |
| Authenticated Owner decisions | Reserved as null in v0.3. An eventual verifier must authenticate the Owner and designated channel independently and bind the decision to the exact action, repository, PR, head and base, scope, expiry and revocation state. |

An observed GitHub `APPROVED` review, including one by Codex, provides no
evidence of independence, historical base coverage, or Owner approval. A
successful CI observation has no independent attestation of workflow baseline,
executed tests, or historical checkout. Neither a review summary nor a content
hash supplies any of those attestations.

## Validation and versioning

The only accepted source version is `geointel-github-observations-v0.2` from
[collector PR #28](https://github.com/bur5/geointel/pull/28) at
`3ada4193588a4c6bcb21b23dd9330831cefd2d86`. It must report a complete,
issue-free, live observation. The bridge validates the decision-relevant
projection and required fields. Upstream validation remains responsible for
raw GitHub pagination, HTTP payload identity, and selection of the latest CI
run. The shape of the legacy export has no effect on the projection.

Each capture is bounded to 120 seconds and its start must be within five
minutes of the trusted clock at handoff. Collections must be sequential with
nonoverlapping UTC seconds. Two captures within the same second are rejected
because v0.2 timestamps have one-second precision. Both include the collector's
internal rechecks of refs and inventory. The bridge checks candidate and job
bindings, source coverage and sequence, CI identities and conclusions, and
review freshness relative to the head. A blocked or partial capture,
unavailable source, mismatched digest, incomplete CI or reviews, or conflict
blocks the entire conversion with a stable error code. The second capture must
agree on the repository, workflow and full PR inventory, including CI and
reviews. Reordering PR, job, or review lists does not change the comparison.

The successful result uses `geointel-manager-input-v0.3`, described by
[its JSON Schema](manager-input-v03.schema.json). Schema validation checks shape.
Use the in-process bridge for source and freshness checks. Manager consumption
must occur in the same trusted call immediately after revalidation. Serialized
copies are for diagnostics. Later assessments require fresh revalidation, and
the two captures provide no atomic guarantee against a subsequent GitHub
change. No operational decision or action is authorized by this version.

The contract uses exact version matching and a pinned source revision.
Unknown versions, producer revisions, incompatible source shapes, and
standalone v0.1 payloads block. A revision upgrade requires reviewing the
mapping and rerunning migration and regression fixtures. Changes to
required fields, their meaning, or the trust boundary require a new contract
version. Fixture inputs are synthetic and have no external authority.

## Governance disposition

[PR #25](https://github.com/bur5/geointel/pull/25) is proposed governance.
This contract preserves its intended boundaries while existing repository
policy governs every real action.

| Tier | Disposition |
| --- | --- |
| R0 | Read-only assessment and advisory output. |
| R1 | Advisory only in v0.3. Autonomous merge is a future capability requiring Owner-approved activation, enforceable required CI, independent review, branch protection, and atomic candidate enforcement. Current merges remain Owner-gated under the proposed policy. |
| R2 | Explicit Owner approval and enhanced independent review are required for merge. |
| R3 | Explicit Owner approval is required before a reserved action. Approval to merge carries no deployment authority. |

## Integration sequence after Owner-authorized merges

1. Confirm what was actually merged from [PR #27](https://github.com/bur5/geointel/pull/27)
   and [PR #28](https://github.com/bur5/geointel/pull/28). Compare the merged
   collector tree to the pinned revision, even if GitHub rewrote the merge SHA.
   If the behavior differs, review and explicitly version any revised binding.
   Keep #27's existing CLI and v0.1 schema available during migration.
2. In a follow-up change, call the merged #28 collector in-process with
   Owner-authorized existing read-only access. Keep the reader and clock outside
   all JSON or Manager control. Feed its native `Snapshot.model_dump()` to the
   bridge. Exercise the native synthetic fixture, plus added/removed PRs,
   forks, non-default bases, head/base movement, and stale or incomplete CI.
   Confirm the same behavior with authorized read-only API testing.
3. Add a v0.3 entry point to the merged #27 Manager. Its inventory must be keyed
   by PR number dynamically, and candidate dependencies must use each PR's
   current head/base binding. Keep task candidates and scope assessments on
   their existing separately trusted input path. The v0.3 bridge does not
   synthesize task candidates, assessments, independent review or Owner
   decisions. Run both versions with fixtures and compare only the overlapping
   advisory semantics. The legacy fixture demonstrates the rejected downgrade.
4. Keep [PR #26](https://github.com/bur5/geointel/pull/26) evidence artifacts
   advisory if that proposal is merged. Any future authority design requires a
   trusted CI baseline, independent reviewer verification, simultaneous
   head/base enforcement at the action boundary, and a separate Owner identity
   and activation review.

The isolated contract imports neither proposal. Runtime API testing and
end-to-end execution with both merged components require that follow-up.
