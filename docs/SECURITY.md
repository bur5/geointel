# Security

Secrets belong in environment variables and are excluded from stored provider configuration, logs and version control. `.env.example` contains names only. Before internet exposure add authentication, authorization, rate limiting, request-size controls and audit logs. Treat retrieved content as hostile data: constrain lengths, prevent prompt injection from granting tools, validate structured outputs, and never execute source text. Database roles should use least privilege; production credentials must differ from Compose defaults. Backups and deletion need explicit controls.

Developer automation permission model: Level 0 read/analyze/propose; Level 1 isolated branch/sandbox writes and tests; Level 2 merge/deploy only after explicit APPROVE. Database deletion, auth, secrets and production infrastructure require extra restrictions. Intended flow: text/voice → interface → developer agent → branch/sandbox → changes → tests/security checks → preview → explicit approve/reject → merge/deploy. Voice is future interface-only functionality and receives no privileged forecasting role.

VIEWS and UCDP payloads are untrusted data only: connector records are length/schema
constrained, are never executed, and grant no tools or code-writing authority. Connector errors
stored in collection metadata are bounded; endpoint credentials must never be embedded in URLs.

Do not deploy v0.0.3 as-is. Report vulnerabilities privately to repository maintainers without
including live credentials or personal data.

ACLED/CAST adapter payloads receive the same hostile-input treatment: strict envelopes and field
lengths, bounded record/response sizes, bounded transient retries, sanitized persisted errors,
and no execution authority. Their current adapters intentionally implement no guessed credential
transport. Operators must review official access terms before adding authentication.

## Strategic-library threat model (v0.0.4)

Operator JSON is hostile data. Pydantic forbids unknown fields, requires attribution/provenance,
bounds identifiers, text, lists, record counts, and local files (1 MB), rejects NULs and duplicate
identifiers, and validates cross-references. Local file loading requires an explicit allowed root to
prevent traversal. There is no URL fetch, archive extraction, template evaluation, dynamic import,
shell invocation, or code execution. Metadata remains JSON data and is never interpolated into
system/tool instructions. Retrieved content grants no tools, permissions, repository writes,
security changes, database deletion, or Red Team bypass. Stored errors are bounded.

Copyright is a separate safety boundary: no corpus or automated scraping is included. Operators
must establish lawful rights; the test fixture is concise original synthetic content explicitly
marked as such. These controls do not provide authentication, malware scanning, content moderation,
or legal clearance. A future model-backed deployment must delimit retrieved content as untrusted,
retain structured IDs rather than trust generated citations, and enforce the same no-tool boundary.

## Validation threat model (v0.0.5)

Validation accepts only an allowlisted packaged suite under a strict, extra-forbidden schema and a 100 KB limit. It does not accept a user-controlled path, fetch URLs, execute fixture metadata, dynamically import modules, render templates, or call live connectors/LLMs. Fixture strings remain data and cannot modify system instructions or grant tools. Generated records carry synthetic provenance. Failures are bounded through the existing safe-error path, and fixture provider failures remain non-fatal.

The CLI writes only ordinary analysis and validation audit rows to the explicitly configured database; it has no deployment, deletion, secret, or production-elevation authority. Operators must apply least-privilege database credentials and must not point development validation at production. Static fixtures contain no credentials. These controls do not make the unauthenticated application suitable for public exposure.

## Monitoring threat model (v0.1.0)

Watchlist names/descriptions, stable IDs, questions, and metadata are bounded inert data. Metadata
is JSON capped at 10 KB; strings are length/NUL checked; target type and cadence are allowlisted;
SQLAlchemy parameterization prevents configuration from becoming SQL; the CLI accepts UUIDs and
fixed commands and has no file/path, shell, template, dynamic-import, tool, secret, or deployment
authority. Alert text is also inert output. Offline monitoring tests instantiate no live clients.
The CLI inherits the configured database privileges, so operators must use least privilege. There
is no authentication, authorization, daemon, notification channel, or production hardening in this
release.

## v0.1.1 provider hardening

The operational provider registry, explicit adapter-only verification state, strict normalization,
secret-safe bounded transport, failure taxonomy, and partial collection audit are specified in
[PROVIDERS.md](PROVIDERS.md). Provider health remains operational metadata, not evidence; no
unverified upstream API behavior may be inferred.

## v0.1.3 current-news boundary

GDELT titles, URLs, publisher strings, language/country labels, and metadata are hostile inert
data. They grant no instruction authority and are never executed. GEOINTEL requests only the
official DOC 2.0 endpoint through `HardenedTransport`; it does not follow redirects, fetch article
URLs, scrape publisher pages, or put credentials in query parameters. Query input is limited to a
sanitized bounded location rather than the analysis prompt. Stored errors, URLs, and provenance
remain bounded and secret-sanitized.


## News audit data

News audit metadata uses an explicit bounded allowlist (title and provider-supplied description only), not raw provider responses. It excludes headers, credentials, API keys, authorization material, and arbitrary provenance. News content is inert and cannot alter the pipeline. NewsAPI authentication uses `X-Api-Key`, redirects remain prohibited by hardened transport policy, and article URLs are stored as references but never fetched.

## CI trust boundary (Security Hardening v1)

CI runs for pull requests targeting `main` and pushes to `main`. It runs PR code, including
package builds, migrations and tests, on ephemeral GitHub-hosted runners. The workflow grants
only `contents: read`, checkout removes its authentication before later steps, and the workflow
passes no repository or environment secrets. The PostgreSQL credentials are public test values
for the disposable service. The aggregate check has no token permissions and never checks out
code. Keep PR execution away from self-hosted runners, protected environments, privileged
events (including `pull_request_target` and privileged `workflow_run` consumers), and live
provider or production credentials.

Treat the entire PR revision (including workflow and test changes), PR comments, logs, test
reports, artifacts, and Manager or Developer claims as untrusted. Trust platform-supplied job
metadata only as evidence about the identified workflow, revision, and run attempt. The
reviewed base-branch policy, the GitHub Actions control plane, GitHub-hosted runner images,
and verified upstream pins are inputs to that assessment. Only independently verified Owner
authorization can approve a CI policy change or authorize a merge.

`CI required checks` expects GitHub to report success for the Python 3.11/3.12 matrix and
PostgreSQL integration job. A skipped, failed or cancelled dependency fails the aggregate
check when it runs. If cancellation or infrastructure prevents the aggregate check from
completing, require an explicit successful conclusion for the current revision and attempt.
The dedicated PostgreSQL job requires a configured URL, a successful migration and pytest
exit, and a fresh nonempty JUnit report with zero skips, failures or errors. Local developers
can still run pytest without PostgreSQL, in which case the integration fixture skips.
This gate detects accidental omissions under the reviewed workflow. A PR can change its
own workflow, assertions, or reports. A green result provides test evidence for review.
GitHub repository rules determine whether this check is enforced at merge time.

Checkout and setup-python are pinned to their upstream release commits. PostgreSQL uses the
Docker Official Image pinned to the digest resolved from `postgres:16`, so the service
cannot change through tag drift. Review and update these pins for upstream security fixes.
The OS image and Python patch versions can change, and the build backend, Python package and
tool version ranges and transitive dependencies are still resolved without an integrity-checked
lockfile. GitHub Actions pip caching is disabled for this workflow. Treat any cache introduced
by future workflows as untrusted input and keep privileged execution isolated from caches and
artifacts written by untrusted jobs.

Before autonomous R1 execution or merging, the Owner must verify the repository and
organization settings that govern PR runs, especially same-repository PR capabilities, fork
write-token and secret policies, runner access, and protected environments. Establish a required
check bound to an independently controlled policy and the exact candidate revision, and verify
Owner approval through a trusted source. Review changes to workflow and test policy, artifact
provenance, and dependency integrity before granting any execution authority. CI status,
comments, and Manager or Developer output confer no authority to dispatch or merge.
