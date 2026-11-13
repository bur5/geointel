# AI Manager v0.2: read-only GitHub state collector proposal

## Status, scope and inspected proposals

This isolated R3-related proposal starts from `main`
`a43ece92adc9c2bdd8652b740b12bdff9623aeee`. It activates no policy or permissions.
The inspected PR heads were:

| PR | Head | Observed status |
| --- | --- | --- |
| [#25: governance](https://github.com/bur5/geointel/pull/25) | `3ff424d086d0577f57c05584af2f0c493c6bd452` | Open; not a GitHub draft; proposed policy remains unmerged. |
| [#26: PR evidence](https://github.com/bur5/geointel/pull/26) | `aca3031b4e78b6ed0197d672c1992be9abfecf24` | Open draft; advisory metadata design only. |
| [#27: Manager v0.1](https://github.com/bur5/geointel/pull/27) | `6b7108de3865692381d9003b9231cdfa4eb92da8` | Open draft; offline planning code remains unmerged. |

No code from those branches is imported, copied or required at runtime. The only
vendored upstream artifact is an unchanged **JSON Schema**, with provenance below,
for compatibility-fixture validation. Existing governance, CI, application behavior,
dependencies, migrations and PR #24/#25/#26/#27 are unchanged.

`geointel.github_state` is a separate package within the existing project. Its
HTTP reader, collection logic and output models can be composed later with a
separately approved Manager integration. It does not implement a planner, network
scheduler, workflow, daemon, AI call, dispatch, review approval, merge or deployment.
No new account, repository, service, paid API or GitHub write permission is created.

## CLI and required access

With the existing project development installation and an **already authorized,
read-scoped** token provided as `GITHUB_TOKEN` by your secret manager/environment:

```sh
python -B -m geointel.github_state
python -B -m geointel.github_state --schema
```

The first command emits JSON on stdout; it never stores credentials or writes a
snapshot file itself. Do not put a token in command arguments, PR content, fixture
files or chat. `--schema` performs no authentication or network activity. Missing
token returns a valid `BLOCKED` report and exit 2 without making any API request.
No `.env` or credential file is loaded by this CLI.

Use repository metadata, contents, pull requests, Actions and checks **read** access
for this repository only. All transport operations are GET. The collector cannot
prove that an externally supplied token lacks broader scopes; the operator must
verify least privilege before use. This proposal does not provision or broaden
access. Do not use a write-capable Developer credential as a substitute for an
approved read-only credential. A GitHub connector already available in chat does
not imply its credentials are available to this CLI.

Only fixed-origin `https://api.github.com/repos/bur5/geointel/...` endpoints and
allowlisted query parameters are permitted. TLS verification remains enabled;
inherited proxy/CA settings are respected. Redirects and foreign pagination/check
URLs are rejected, not followed with credentials. No arbitrary URLs, repository
code, provider data, shell commands or PR-supplied instructions are executed.

## Native validated snapshot

The [packaged schema](../src/geointel/github_state/snapshot.schema.json) describes
`geointel-github-observations-v0.2`. Strict Pydantic validation and semantic checks
run before output. Schema validation alone cannot establish source authenticity.
The native inventory uses positive PR numbers rather than a fixed PR allowlist.
It includes all open PRs within bounded collection limits, including new proposals.
It never silently projects away additional PRs.

The report records:

- Repository ID/name/private status and default branch/SHA.
- Open PR number, head repository/SHA, base branch/SHA, draft status and update time.
- Existing CI workflow identity, selected run/attempt, reported PR head/base
  association, raw status/conclusion and normalized states; job/check IDs, App
  identity, timestamps and matched metadata. Existing observation inventory is
  `.github/workflows/ci.yml` and the three current CI job names. This is not a
  discovery or modification of mandatory merge gates.
- Review ID, account ID/login/type, API review state, submitted time and commit ID.
  `APPROVED` is a GitHub review state, not proof of Owner authorization or reviewer
  independence. Both verification fields are always false. Historical review base
  and actual CI checkout are explicitly unverified.
- UTC start/end and per-response capture times; method, endpoint, allowlisted query,
  page, HTTP status, GitHub request ID, server Date and canonical response digest.
- Fixed issue codes, partial observations on failure, a local content digest and
  an explicit compatibility result for the frozen Manager v0.1 contract.

API metadata comes through authenticated HTTPS with freshness/provenance checks;
that is distinct from trusting author-controlled assertions. PR/review endpoint
responses necessarily contain some prose in memory. The transport hashes the JSON
response for provenance, but descriptions, review bodies, comments and AI summaries
are excluded from snapshot fields and authority decisions. Comment endpoints are
never requested. No raw body, HTTP headers, token or exception text is logged or
included in errors. Error responses are not ingested as evidence.

`OBSERVED` / exit 0 means the requested metadata observation completed consistently,
not that CI semantics, scientific validity, independent review, Owner approval or
merge readiness were established. `advisory` is always true and `action_authorized`
is always false. Green CI and a local hash grant no authority. An attacker can
forge or recompute a local report/hash; consumers must establish provenance outside
the report rather than trusting its self-asserted fields.

## Consistency, freshness and failure handling

The collector reads inventory and PR details, checks their agreement, re-reads PR
refs and review metadata, then rechecks full inventory, every observed base branch,
repository identity/default branch and CI workflow. Each CI run/attempt is checked
again after job/check collection. Changed heads, bases, draft/inventory state or
review state fail closed. These bounded re-reads are **not an atomic GitHub snapshot**
and cannot guarantee that nothing changes afterward. No merge-time guarantee is
claimed; a future consumer must check a current clock/refs again before decisions.

CI runs must be pull-request runs of the selected workflow, bound to the observed
repository, PR head/base and head repository. Jobs are read for the exact run
attempt and cross-checked with their GitHub Actions check-run App ID `15368`/slug
`github-actions`. Same-named commit-status contexts and other Apps cannot substitute.
The collector does not independently execute tests, verify workflow/test-selection
semantics, or attest a historical checkout. A future Owner-reviewed gate must add
trusted workflow/baseline and reviewer isolation separately.

States remain `success`, `failure`, `pending`, `skipped`, `unknown`; neutral or
unrecognized conclusions are unknown. Missing jobs/runs, pending/skipped/failed CI,
malformed data, stale/future timestamps, conflicting App/SHA metadata, denied
access and incomplete pagination yield `BLOCKED`, never a success fallback.
Historical reviews for a different head conservatively block the snapshot even if
another review supersedes them; resolving that history is a future policy decision.
An empty review list is a complete observation of no reviews, not independent
approval. A matching review head does not establish its historical base binding.

Bounds: 25 open PRs, three pages of 100 records per list, 200 GET requests,
1 MiB per response, 10-second HTTP timeouts and a 120-second collection deadline.
The deadline is checked during requests/streaming; an in-flight read can take up
to the socket timeout to fail. Reviews/jobs are bounded by their paginated limits.
A full terminal page without completion evidence is treated as ambiguous. HTTP
Date must be within 300 seconds of the supplied UTC clock and successful responses
must include a GitHub request ID. Clock drift/cached metadata may therefore block.

No retries, polling, sleeps, recurring jobs or automatic resumption are implemented.
429 and rate-limited 403 stop with a fixed reason; rate/reset headers never trigger
more requests. The run consumes ordinary existing GitHub API quotas; it creates no
Actions job or additional paid service. Operators must respect available quotas
and authorize any later credential/orchestration changes separately.

## Compatibility boundary with Manager v0.1

There is a real upstream mismatch: Manager v0.1 accepts exactly the open unresolved
inventory #24/#25/#26 and only `main` refs. Current GitHub inventory already includes
#27 and will also include this proposal. Exporting only three PRs would hide an
unresolved dependency and weaken the proposed policy. This collector refuses it.

`manager_v01.payload` is therefore null with explicit reasons whenever observations
are incomplete, inventory differs from exactly #24/#25/#26, the default branch is
not `main`, or any PR has another base. Native observations retain all collected
PR metadata, including non-main bases. New PRs do not break the native schema.

For a representable **synthetic** case only, the data adapter emits the existing
v0.1 input shape with no candidates or scope assessments, evidence status
`observed` and provenance `unverifiable`. It does not invent `operator_attested`
evidence, sign approvals or compute an authorization pin. Even a matching hash
cannot make that payload authorize work: v0.1 would block on unverifiable provenance,
missing attested refs and zero eligible work. CI/review details stay in the native
report; they are not relabelled as work-item or scientific evidence.

Fixtures:

- [Native observation](collector-examples/native-observation.json): mocked API
  capture with #24/#25/#26/#27 and blocked v0.1 export. `transport: mock` is explicit.
- [Legacy-shaped observed input](collector-examples/manager-v01-observed-input.json):
  a **different** mocked inventory containing exactly #24/#25/#26; not a lossy
  projection of the preceding fixture and not real repository evidence.
- [Frozen upstream input schema](collector-examples/manager-v01-input.schema.json):
  copied unchanged from PR #27 commit `6b7108de3865692381d9003b9231cdfa4eb92da8`,
  path `src/geointel/manager/schemas/input.schema.json`, SHA-256
  `0f26697b71833bcac9dd87353da9c171b3ac815856498a26ec579c2915a68f35`.

Native output is validated at runtime. Legacy projection shape/fixtures are checked
against the frozen schema in local validation, without installing or copying the
unmerged Manager implementation. The runtime adapter constructs fixed schema-shaped
data from validated metadata; it does not run the upstream Manager model/engine
or a JSON Schema validation service. Tests detect fixture and schema drift.

Next integration requires an explicit Owner-reviewed Manager contract/version
supporting arbitrary PR inventories and preserving unresolved dependencies. It must
separate API observation authenticity from authenticated Owner scope/approval,
scientific integrity and independent review, and define report freshness, trusted
clock, durable provenance and ref revalidation. Do not silently relax v0.1 literals,
pretend a schema-valid fixture is an approval, or dispatch from this collector.

## Validation and operational follow-up

```sh
python -B -m pytest tests/test_github_state.py
python -B -m unittest discover -s tests -p test_github_state.py
ruff check src/geointel/github_state tests/test_github_state.py
ruff format --check src/geointel/github_state tests/test_github_state.py
```

Mocked tests cover pagination/bounds, API errors/rate limits, missing CI, distinct
conclusions, head/base changes, stale/dismissed reviews, spoofed approval prose,
wrong App/check URL, clock/HTTP freshness, denied access and dynamic inventories.
They use no real credentials or network. The new tests join existing pytest
discovery without any workflow change. The standalone path needs no database.

At implementation time no `GITHUB_TOKEN` was provisioned for the CLI. Actual PR
heads were inspected through the existing connected GitHub read tools; this does
not count as a live end-to-end HTTP collector run. Before operational reliance,
use an existing authorized read-only token to verify actual API response schemas,
check-run SHA/App bindings, HTTP provenance headers, limits and field-for-field
correspondence to GitHub. Test fork/deleted-head behavior only when such cases
already exist or receive separate authorization. Absence of needed access remains
blocked; do not create accounts, increase permissions or buy services to bypass it.
