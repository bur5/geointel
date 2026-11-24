# GEOINTEL experimental verifier

This isolated experiment models a CI verifier and an atomic merge target.
It uses synthetic data and the Python standard library. It makes no network
calls and has no dependency on the application repository.

## Reproduce

Run these commands from this directory with Python 3.12.

```sh
sha256sum -c SHA256SUMS
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v
```

test-evidence.txt preserves the earlier test run. reproduced-test-evidence.txt
records a fresh run during preservation.

## Design

Candidate binds repository ID, PR number, head, base, integration commit and
policy. Run adds workflow identity, run ID and attempt. Job evidence binds the
run, mandatory name, job ID and conclusion. The gate rejects incomplete or
ambiguous evidence and clears the previous verdict as soon as the authoritative
dispatcher registers a newer attempt. Two authenticated roles are modeled
separately. Candidate movement invalidates both approvals and CI. A generation
counter prevents approval replay if the same candidate values later return.
A shared lock serializes validation, ref or attempt changes and simulated
merge. The tests exercise races after a caller takes its final snapshot.

## Limits and requirements for further work

Inputs represent trusted adapters. No GitHub API, webhook authentication,
identity verification, runner isolation, credentials, durable storage, or
real merge operation is implemented. The test's shared lock has no authority
over GitHub refs or check state. Live activation would need independently
controlled tests and publishing, isolated execution without publisher
credentials, reconciliation of authoritative attempts and refs, durable
transactional state and audit records, and a merge mechanism that verifies
both approved refs at the operation itself. An App check or an expected-head
GitHub PR merge request does not by itself supply that transaction.

Keep this work separate from the production repository and the governance PRs.
