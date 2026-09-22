# Provider operations (v0.1.1)

Provider configuration and health are operational metadata, never geopolitical evidence. No
provider is enabled by default and no connector falls back to a guessed endpoint.

| Provider | Role | Live mode | Verification status | Auth | CI mode |
|---|---|---|---|---|---|
| UCDP | observed/historical conflict evidence | operator adapter | OPERATOR_ADAPTER_REQUIRED | adapter/operator must verify | fixture |
| ACLED | observed/reported operational events | operator adapter | OPERATOR_ADAPTER_REQUIRED | adapter/operator must verify | fixture |
| VIEWS | predictive model output | operator adapter | OPERATOR_ADAPTER_REQUIRED | unknown; operator must verify | fixture |
| CAST | predictive model output | operator adapter | OPERATOR_ADAPTER_REQUIRED | unknown; operator must verify | fixture |

## Verification record

On 2026-09-22 this environment attempted authoritative-document discovery, but the network search
service returned HTTP 401. Consequently **no direct live API contract was verified or
implemented**. These official starting references are recorded for human review, not represented
as verified contracts:

* UCDP: <https://ucdp.uu.se/apidocs/> and <https://ucdp.uu.se/downloads/>
* ACLED: <https://acleddata.com/acleddatanew/wp-content/uploads/dlm_uploads/2023/06/ACLED-API-Documentation.pdf>
* VIEWS: <https://viewsforecasting.org/>
* CAST: <https://www.giga-hamburg.de/en/research-and-transfer/projects/cast-conflict-forecasting>

A human must review current documentation, access terms, licensing, authentication, field
semantics, versions, pagination, and rate limits before connecting an adapter. Do not point these
settings at an upstream service unless its responses have deliberately been mapped to the internal
schema.

## Explicit modes and registry

Modes are `OFFICIAL_API`, `OPERATOR_ADAPTER`, `FIXTURE`, and `DISABLED`. The current runtime uses
only `OPERATOR_ADAPTER` (when explicitly configured) and `DISABLED`; fixture mode is reserved for
offline test inputs. `GET /providers` and `python -m geointel.providers capabilities` expose the
secret-free registry. `status` is an alias for the same safe snapshot. `check PROVIDER` validates
configuration state only and never contacts a provider or starts collection.

The registry records connector/schema versions, documentation status and references, epistemic
role, configuration/enabled state, verified geography/temporal capabilities (empty when unknown),
pagination/rate-limit knowledge, and bounded health text. Dependency fields are empty rather than
inventing provider independence or common upstream sources.

## Configuration and network policy

Existing provider variables remain compatible. Enabling a provider requires its configured base
URL and endpoint path. Shared bounds are `PROVIDER_MAX_PAGES` (default 10),
`PROVIDER_MAX_RECORDS` (10000), and `PROVIDER_MAX_RESPONSE_BYTES` (5000000). HTTPS absolute URLs
without embedded credentials are required. Loopback, link-local, private, reserved, and metadata
IP addresses are rejected by default. `PROVIDER_ALLOW_PRIVATE_NETWORKS=true` is the explicit opt-in
for a controlled internal adapter; it does not permit `file://`, embedded credentials, or HTTP.
DNS rebinding must additionally be controlled at deployment egress/firewall level.

Credentials, if an operator adapter needs them, must be supplied through environment/secret
management. They are never registry fields or persisted configuration. URLs are sanitized before
provenance retention; query keys resembling tokens, keys, signatures, or credentials are redacted.
Authorization/cookie-like mapping values and exception text are bounded and redacted.

## Hardened transport

`HardenedTransport` provides bounded connect/read behavior, at most five configured retries,
deterministic exponential backoff, bounded `Retry-After`, explicit 429/5xx/auth categories, JSON
content-type checks, response-size limits, TLS-backed HTTPS validation, and no redirects. Disabling
redirects prevents redirect-to-private-host attacks. Tests inject `httpx.MockTransport`; CI has no
network or credential dependency. Authentication/authorization failures are never retried.
Compressed-response safety is enforced by the decoded response byte bound; operators should also
bound ingress at their adapter/reverse proxy.

## Schema and collection boundary

The internal adapter schemas are strict (`extra=forbid`). UCDP records normalize only into
historical `NormalizedEvidence`; ACLED records into reported `NormalizedOperationalEvent`; VIEWS
and CAST into distinct `NormalizedForecastSignal` records. Prediction values retain native unit
and scale and are never relabeled probabilities. Geographic/horizon mismatch is disclosed, not
aggregated or transformed. Provider event/issue/update and retrieval timestamps occupy distinct
fields; unknown recency remains unknown.

Raw metadata is the validated model only, recursively depth/item bounded and secret-sanitized.
Long text has field-level limits. Exact provider IDs deduplicate deterministically; there is no
fuzzy or cross-source deduplication.

The reusable cursor collector applies only to an explicitly documented operator-adapter cursor
contract. It stops on an empty page, absent cursor, repeated/malformed cursor, maximum pages, or
maximum records. `CollectionAudit` reports request/page/received/accepted/rejected/duplicate
counts, truncation, bounded rejection reasons, rate limiting, categorized failure, and `PARTIAL`
status while retaining valid earlier records. No undocumented upstream pagination parameter is
inferred.

## Provider limitations

* **UCDP:** observed/historical only. The legacy adapter schema is strict; the configured dataset
  version is preserved. Direct upstream query and pagination semantics remain unverified.
* **ACLED:** reported events only. Fatalities are explicitly reported estimates, not perfect ground
  truth. Direct authentication, licensing, fields, pagination, and limits remain unverified.
* **VIEWS:** predictive only. Model/version, issue and target dates, geography, horizon, target,
  prediction, unit, and scale are mandatory adapter semantics. No conversion or aggregation occurs.
* **CAST:** predictive only and semantically separate from VIEWS despite shared mechanics. Direct
  machine access and provider semantics remain unverified.

Provider failures flow through collection/source-health metadata to reasoning and monitoring
guardrails. They are not events, evidence, detected geopolitical changes, or escalation alerts.
No migration 0008 is needed: v0.1.0 `AnalysisRun.collection_metadata` already stores the bounded
per-run audit without semantic overload, while the registry is configuration-derived and must not
persist credentials.
