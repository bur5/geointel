# Collection coverage v1

The pipeline stores this contract at `AnalysisRun.collection_metadata.collection_coverage`
in the existing JSON column. The pipeline and monitoring use
`geointel.coverage.CoverageDecision`. This contract describes provider retrieval and the
eligibility of individual records. A provider snapshot can omit real-world events.

## JSON schema

The root has `version` (integer `1`), `evaluated_at` (UTC ISO 8601 timestamp), and
`collections` (ordered array). Each entry covers one connector invocation, identified by
`collection_id` (string `<analysis-run-uuid>:<zero-based invocation index>`). Repeated
invocations of one connector have separate identities. Pages and media query families
belong to their invocation and are represented in its retrieval evidence.

| Entry field | JSON type and meaning |
| --- | --- |
| `collection_id`, `connector` | Strings identifying the invocation and connector. |
| `state` | One of the six values below. |
| `requested_geography` | Original geography string submitted to the analysis. |
| `requested_scope` | Scope object the analysis requested, using canonical geography when available. |
| `actual_query_scope` | Scope sent to the provider or adapter, or null when unavailable. Provider-specific filters and exact media timestamps are retained in retrieval evidence. |
| `verified_scope` | Scope attested by the connector, or null. |
| `gaps` | Array of codes. Codes include `provider_restriction`, `incomplete_retrieval`, `pagination_unverified`, `retrieval_failed`, and `assessment_scope_unverified`. |
| `provider_release`, `provider_versions` | Release string or null, and an array of distinct supplied forecast model version strings. Connector and response-schema versions are in retrieval evidence. |
| `retrieval_evidence` | Connector audit object or null. The audit includes integration mode, connector/schema versions, timing, request/page/row counts, rejection details, restrictions, truncation, pagination ambiguity, and per-page evidence where collected. An optional `verification` contains `scope`, `basis` and `pagination_exhausted: true`. |
| `error_causes` | Array of distinct failure categories, failure messages and bounded rejection details. |
| `event_counts` | Object described below. |
| `records` | Array of assessment diagnostics for retained operational events, forecast signals and media reports. |

A scope contains `kind` (`events`, `historical_release`, `forecast`, `media`, or
`unspecified`), `geography` (string), `start` and `end` (inclusive ISO dates or null),
`horizon_months` (positive integer or null), and `release` (string or null). Null dates
are unspecified. The current operational event scope is the UTC assessment date and
the preceding 90 calendar dates. Forecast assessment uses the requested calendar-month
horizon. Media query geography is a search parameter.

`event_counts` contains `retrieved`, `rejected`, `duplicate`, `eligible`, and `confirmed`.
Retrieved and rejected counts are nullable integers. In a dedicated event or historical
release audit they count provider rows, including normalization rejections and duplicates.
An unaudited count can reflect normalized events delivered to the pipeline. Duplicate
counts include known audit and pipeline discards, including repeat identities across
connector invocations. Eligible counts describe individual operational event records
within each invocation. These counters overlap and cannot be summed to obtain a
cross-provider unique event total. Confirmed is null unless the verified provider query
supports a scoped zero, which is serialized as integer zero. The current connectors
supply no independent confirmation of positive real-world event counts.

Each record contains `kind` (`event`, `forecast`, or `media`), `provider`, `record_id`,
`geography`, `observation_time`, `publication_freshness`, `forecast_issuance`,
`forecast_target`, and `eligible` (boolean). Each check is `pass`, `fail`, `unknown`,
or `not_applicable`. Provider identity and record ID are used within each kind.
Across collections the analysis and monitoring use the first retained copy.

## Decision rules

| State | Rule |
| --- | --- |
| `not_attempted` | Connector disabled for the invocation. |
| `failed` | Retrieval failed and no normalized rows were returned. |
| `partial` | Known restriction, rejection, limit or interrupted retrieval. Rows returned before the interruption remain persisted and are evaluated individually. |
| `complete_empty` | Audited successful query with an explicit verified scope, reconciled counts, clear pagination and zero retrieved rows. |
| `complete_with_records` | Same verified conditions, with at least one retrieved row. |
| `unknown` | Remaining cases, including success without verification, an ambiguous terminal page, and missing or unsupported legacy contract data. |

A verified query requires successful audit status, page evidence, clean termination and
scope matching the verification assertion. ACLED currently requires an explicit terminal
null cursor and an explicit unrestricted recency marker on every page, with no other
restriction keys, a canonical mapped country query and any retained rows inside query
scope. Research-tier restrictions apply even when rows are present. Missing terminal
markers are ambiguous. Repeated cursors and later-page failures preserve earlier rows
and prevent certification. UCDP requires consistent declared page and row totals,
reconciled row counts, mapped country identity, and clean traversal without duplicate
IDs or empty interior pages. The resulting verified scope is retrieval of a particular
country release. It supplies no operational date coverage and no zero-event claim.
CAST, VIEWS and media success remain unverified in v1.

A confirmed zero additionally requires `complete_empty` with actual, verified and
requested scopes exactly equal and of kind `events`. This count describes records
returned by that provider for that query at collection time. Multiple collection entries
remain independent. The contract emits no aggregate zero claim.

An operational event must have a mapped matching country, nonempty identity and event
type, and occurrence in the operational date window with occurrence at or before retrieval
and retrieval at or before assessment. The update timestamp is retained separately.
Publication freshness is unknown when the source supplies no original publication time.
For media only, publication freshness checks the 90 days preceding assessment and
publication <= retrieval <= assessment. Media remains discovery material and uses the
existing news relevance workflow.

A forecast signal must have a mapped matching country-level footprint and a usable
identity, finite value and target variable. Issuance must be at or before retrieval,
retrieval at or before assessment, and issuance within 45 days. Target validity
independently requires issuance <= target start <= target end and overlap with the
assessment horizon. Subnational records without an exact country footprint remain
available for audit. Historical evidence uses the existing historical context path.

The API's existing collection outcomes, counts and availability booleans retain their
ingestion and transport meanings. The persisted analyst inventory includes retained
operational and forecast records with explicit audit-only descriptions for excluded rows.
Downstream assessment inputs use the shared eligibility decision. Legacy monitoring
diagnostics retain their existing row-health and freshness meanings, including operator
thresholds. The new coverage projection is the assessment-time snapshot and is surfaced
in the health report. Watchlist changes compare eligible operational and forecast records
when both snapshots contain v1 decisions; legacy comparisons retain their behavior.

## Projection for future PR #42 integration

Read `CoverageDecision.from_metadata(run.collection_metadata).projection()`. To get
only one connector's entries, pass its name to `projection(connector)`. The projection
contains `version`, `evaluated_at`, `state`, and `collections` in the schema above.
The summary state is the entry state only when exactly one entry matches. With zero or
multiple matches it is `unknown`. Absence of a recognized contract produces an empty
projection with null evaluation time and unknown state. Consumers should use the
individual entries and exact scopes for any zero claim. Use `eligibility()` for the
first-retained-record selection shared by analysis and monitoring. This integration
requires no reads from provider APIs and no database migration.

## Independent review

- Compare the exact pre-change PR head and verify that only the draft branch advanced.
- Inspect the provider contracts and entitlement evidence behind ACLED and UCDP verification.
- Replay complete, restricted, rejected, repeated-cursor and failed-later-page fixtures.
- Verify that canonical mapping, UTC event dates, release identity, forecast issuance and
  target validity retain distinct meanings and that ambiguous cases cannot produce zero.
- Compare legacy API responses and persisted rows, then inspect SQLite and PostgreSQL
  JSON round trips and the monitoring projection.
- Inspect assessor inputs and monitoring changes using stale or out-of-scope records.
- Confirm that scoped provider zeroes and historical release retrieval are never presented
  as claims about all real-world events.
