# AI Manager v0.1: offline advisory task-contract planner

## Scope

This isolated proposal starts from `main` a43ece92adc9c2bdd8652b740b12bdff9623aeee.
The proposed target policy is [PR #25 at 3ff424d](https://github.com/bur5/geointel/tree/3ff424d086d0577f57c05584af2f0c493c6bd452),
not merged governance. [PR #26](https://github.com/bur5/geointel/pull/26) was inspected
as an advisory metadata design, not imported or depended upon. Neither PR is
modified. Planning/authority logic is itself protected-policy-related; merging or
applying it remains subject to Owner authorization and independent review.

`python -m geointel.manager` is a deterministic local Python CLI. It consumes a
bounded JSON snapshot and candidate list, ranks work, raises risk conservatively
and drafts at most one Developer task contract. It never initiates or approves
work. It does not read Git, call GitHub or AI, execute shell commands, consult
credentials, create resources, schedule jobs, persist state, dispatch tasks,
review code independently, merge, deploy or change repository settings.
No workflow, dependency declaration, migration or existing governance file changes.
Pydantic v2 is already supplied by the project's existing dependency stack.

## Trust and determinism

All descriptions, issue/PR text and external evidence are untrusted data. Candidate
prose is hashed, not copied into contract instructions. A small hint detector can
only raise risk; it does not understand arbitrary prose or certify intent. The
engine generates acceptance/verification/stop text from fixed templates and uses
literal validated paths. No input-supplied command is executed. Do not include
secrets in input. Provenance references allow bounded URNs or repository GitHub
URLs without userinfo/query parameters; references are never fetched.

JSON validation checks structure, types, lengths and allowlisted effects. It does
**not** prove the snapshot is true. Before drafting a contract, the caller must
supply `--expected-snapshot-sha256` through a trusted channel, after independently
checking the snapshot's source, scope assessments and evidence. The pin covers
canonical validated snapshot data, not candidate self-claims. A digest establishes
integrity relative to that external decision, not cryptographic identity or Owner
approval. Merely computing a digest from attacker-supplied data establishes no
trust. No pin, wrong pin or `unverifiable` provenance produces `BLOCKED`.

The timestamp `evaluation_at` is an explicit input, not the wall clock. Both the
snapshot and source evidence must be no more than 3600 seconds old at that time;
evidence cannot postdate capture. Every evidence/candidate head/base must match
the snapshot. Contradictory claims, stale refs and duplicate evidence IDs block
planning. The offline engine cannot discover live ref movement or verify a clock:
a future trusted caller must supply a current UTC clock and revalidate refs before
any separately authorized action. A successful plan says nothing about freshness
after its evaluation time. No live snapshot or authenticated Owner approval is
asserted by the bundled examples.

Canonical JSON uses sorted keys, ASCII escaping, compact separators and no NaN.
Snapshot/input SHA-256, task IDs and plan IDs are stable for identical validated
inputs and the same external pin. List order is part of the input. Task IDs include
the engine/policy version, complete candidate and snapshot hash. Changed evidence
or candidate content changes the ID; IDs are not an authorization or lease.
The engine does not mutate its input or read time/randomness/environment state.

## Input and output contracts

The packaged [input schema](../src/geointel/manager/schemas/input.schema.json) and
[output schema](../src/geointel/manager/schemas/output.schema.json) are generated
from the strict Pydantic models and use JSON Schema 2020-12 semantics. Unknown
fields, control characters and coercions are rejected. Semantic cross-field checks
remain in the engine, not in JSON Schema alone. Maximum input is 1 MiB, 32 candidates,
32 attested scope assessments, 100 evidence records and 20 paths/effects/dependencies
per item. The JSON loader rejects duplicate object keys and non-finite numbers.
Files must be explicit regular `.json` files, not symlinks, or stdin (`-`).

Input includes:

- Repository/private status, captured/evaluation times, head/base SHA and source
  provenance; these are assertions to be checked by the caller, not discovered facts.
- Structured evidence IDs, topic, subject, value, source/ref/time, observation status
  and refs. Only caller-attested work-item evidence for that task can support it;
  CI/review comments cannot substitute for scope evidence or approvals.
- Separately attested assessments binding category, mode, paths, effects, minimum
  risk, classification clarity, scientific-boundary status and evidence IDs.
- An explicit unresolved inventory of open PR #24, #25 and #26. v0.1 cannot mark
  these resolved. Future resolution needs a new verified snapshot contract/version.
- Candidate key, bounded prose, structured category/mode/scope, claimed risk,
  refs, evidence IDs, dependencies and effort (1–5). Claims cannot expand authority.

Output always contains `advisory: true`, `action_authorized: false` and
`independent_reviewer: false`. `CONTRACT_PROPOSED` means only that a draft contract
can be reviewed, not that Developer may start it. All other cases are `BLOCKED`;
there is no ready/approved/merge-ready state. Invalid input produces a sanitized
blocked report without echoing payloads, filesystem errors or validation internals.

The report includes caller-attested snapshot provenance and hashes, refs, ranked
items with rule-code rationale/blockers, dependencies, and a sequenced decision
audit. The optional contract supplies objective, literal scope, risk, evidence,
acceptance criteria, verification plan, stop conditions, fixed authority boundaries
and a maximum of two corrective iterations for any future authorized execution.
No retry or execution loop is implemented. Titles/descriptions and candidate
commands are never promoted to trusted instructions. Do not execute contract
prose or dispatch based on `ELIGIBLE_FOR_CONTRACT`.

## Risk, priority and unresolved work

Risk is the maximum of the candidate label, attested floor, structured effects,
mode, conservative path rules and escalation-only text hints. A claimed R0 cannot
lower a trusted R3. Candidate scope and evidence must exactly match the attested
assessment. Classification disputes/uncertainty block the affected task for Owner
determination. Unknown/violated scientific boundaries also block and escalate.

- R0: bounded read-only assessment.
- R1: isolated reversible proposals within unchanged approved boundaries, such
  as ordinary Markdown documentation. A new authorized task is still required.
- R2: model/evidence/architecture/persistence/security implementation, requiring
  enhanced independent review. v0.1 cannot verify that review and blocks selection.
- R3: protected policy, authority, gates, reviewer identity, permissions/secrets,
  trust boundaries, scientific integrity, deletion, spending, deployment, public
  release or integrations. v0.1 cannot verify Owner authorization and blocks
  selection. In particular, this CLI cannot authorize changes to itself.

For modification proposals, governance/security files, `.github/`, `tests/`, the
manager package and dependency declarations conservatively escalate to R3;
application/migration paths escalate to at least R2. Unknown modification paths
require Owner classification. This is intentionally over-conservative; matching
an innocent-looking path never proves semantic safety. Reading an existing CI
file as an R0 assessment does not imply changing gates or depending on PR #26.

Priority is deterministic: security/integrity defects, CI reproducibility,
infrastructure blockers, documentation, then product improvements; within a class,
smaller effort then stable task ID break ties. Rankings are not objective risk
scores or scientific judgments. The highest *eligible* item is selected, skipping
blocked higher-priority proposals. Duplicate keys or identical structured scopes
block all duplicates. Candidate dependencies are never executed/resolved here:
`task:<key>` remains unresolved even if another candidate is eligible.

Model/evidence effects add PR #24; R3 adds PR #25; gate changes add PR #26.
Explicit dependencies always block until handled outside v0.1. Open/draft status,
green CI and advisory comments never resolve them. No task may change or merge
PR #24/#25/#26 automatically. Independent unblocked R0/R1 planning may continue.
Preserve provenance, uncertainty, synthetic labels and the separation of historical
observations, current evidence, reporting, inference and forecasts. This planner
produces no evidence, forecast, calibrated probability or scientific conclusion.

## CLI and synthetic example

From an existing development install (`pip install -e '.[dev]'`), inspect schemas:

```sh
python -m geointel.manager schema input
python -m geointel.manager schema output
python -m geointel.manager plan docs/manager-examples/input.json
```

The last command intentionally returns exit 2 (`BLOCKED`) without a trusted pin.
For the **synthetic demonstration only**, the known snapshot pin is:

```sh
python -m geointel.manager plan docs/manager-examples/input.json \
  --expected-snapshot-sha256 44b204d3c7c81fa7b621d1afff0d8301a93f9222d03de9058e649d6de8bed04b
```

Compare with [example output](manager-examples/output.json) for the corresponding
[example input](manager-examples/input.json). All refs, evidence and attestations
in these examples are synthetic; they do not assert actual repository state.
The policy proposal is raised from claimed R0 to R3 and blocked on PR #25/Owner
authorization. The selected R0 task is `assess-ci`:

- Inspect `.github/workflows/ci.yml` for CI reproducibility within read-only scope.
- Cite supplied evidence/refs and distinguish observations from inference.
- Report missing checks and limitations; make no file or workflow changes.
- Stop on stale refs, uncertain scope, secrets, required access or unresolved evidence.
- State is `PROPOSED_NOT_AUTHORIZED`; obtain a separate task authorization before work.

`snapshot-digest INPUT` prints canonical snapshot SHA-256 and
`trust_established: false` for inspection. It is not an attestation service.
Exit 0 for a proposed contract or schema/digest inspection; exit 2 for blocked or
invalid planning input. CLI syntax errors use argparse's normal exit 2/help.
Output is JSON on stdout; the CLI has no output-file option or persistence store.

## Verification and future integration

```sh
python -m pytest tests/test_manager.py
python -m unittest discover -s tests -p test_manager.py
ruff check src/geointel/manager tests/test_manager.py
ruff format --check src/geointel/manager tests/test_manager.py
```

The tests cover risk escalation, self-label downgrade attempts, stale clocks/refs,
contradictory evidence, duplicate records/tasks, unresolved dependencies, scientific
violations, injection text, schema bounds, deterministic repeated CLI output and
zero eligible work. They do not access GitHub, providers or databases. The existing
pytest discovery includes them without workflow changes; standalone unittest avoids
application-wide conftest setup. Schema tests detect checked-in/model drift.

A future Owner-approved orchestrator may call the pure `plan()` function, validate
its versioned output and persist a decision record. It must independently supply
trusted snapshots/current clock, authenticate Owner authorization, verify reviewer
identity, resolve dependencies, enforce exclusive ownership/idempotency and recover
actual remote state before any dispatch. Persisting a plan or having a matching
hash is insufficient. Review/merge gates, quota enforcement, cloud scheduling,
rollback and restart safety remain unimplemented; no laptop-independent service
is established by this CLI. No integration with unmerged PR #26 exists.
