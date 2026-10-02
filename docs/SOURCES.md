# Source and connector policy

Connectors validate untrusted data, use bounded retries/timeouts, retain provenance, and cannot execute retrieved content. Failures are stored as bounded safe messages and do not abort otherwise valid analysis. Each run reports per-connector attempted, status, success, normalized-record count, and failure reason; disabled connectors are explicit and all-source failure never masquerades as live intelligence.

## UCDP

UCDP supplies historical/conflict evidence. Official `gedevents/<version>` collection resolves a
human location through the finite reviewed country table and sends its numeric Gleditsch-Ward code
as `Country`; unknown/ambiguous locations stop before HTTP. The initial verified mappings are Spain
230, Georgia 372, Taiwan 713, Serbia 340, and Nigeria 475, as documented by the UCDP API country
code list/codebook linked from the [official API documentation](https://ucdp.uu.se/apidocs/).
These identifiers and aliases are provider lookups, not sovereignty judgments.

Annual GED (default 26.1, through 2025) is historical/base-rate evidence and never current
operational coverage. A separately configured Candidate version has the explicit
`candidate_recent` role and approximately one-month publication lag; it is not real time. Dataset,
version, temporal role, requested geography, resolved code, and fatalities (`best`/`low`/`high`)
remain in provenance. Missing records never establish absence. A UCDP artifact is Evidence, not
automatically an Event.

## VIEWS

VIEWS contributes independent machine-learning forecast signals. Network access in the implementation environment did not permit authoritative endpoint verification, so v0.0.3 deliberately ships no claimed public endpoint and no real/offline forecast values. Tests use deterministic records labelled synthetic.

An enabled deployment must provide a verified adapter endpoint. The internal `geointel-views-adapter-v1` JSON contract is an implementation boundary, **not a claim that VIEWS publishes this schema**:

```json
{"forecasts":[{"id":"provider record id","model":"model name","model_version":"version or null","geographic_unit":"country/grid/etc","location":"provider location","issue_date":"ISO-8601","target_start":"ISO-8601","target_end":"ISO-8601","horizon_months":12,"target_variable":"provider target","prediction":0.0,"unit":"provider-declared unit or null","scale":"provider-declared scale or null"}]}
```

The adapter must map official documented fields without inferring semantics. GEOINTEL stores record/model identity, geography, dates/horizon, target, prediction, units/scale, retrieval time/URL, schema marker, and alignment results. It does not call a prediction a probability unless the provider's documented unit says so—and even then it remains a provider signal, not a GEOINTEL probability.

Location mismatch, non-country resolution, and horizon mismatch are surfaced. Values are retained without aggregation. Live enablement requires human verification of current VIEWS documentation and licensing plus a reviewed field mapping; secrets, if later required, must use environment variables and must never enter provenance or logs.

## ACLED operational events (v0.0.3)

ACLED is observed/reported operational event input, not a forecast. Live official access was not
verified in the implementation environment, so the connector is disabled and accepts only an
operator-reviewed adapter. `geointel-acled-adapter-v1` is an internal contract—not a representation
of an official ACLED endpoint or schema. Its strict envelope is `{"events": [...]}`. Records use
`event_id`, `event_date`, `event_type`, and `country`, with optional `sub_event_type`, `admin1`–
`admin3`, `location`, coordinates, `actor1`/`actor2`, associated actors, `fatalities`, `notes`,
`source`, `source_scale`, `disorder_type`, and `timestamp`. Raw validated adapter metadata,
retrieval URL/time, source ID, and uncertainty markers are retained. Fatalities are reported
values and are not asserted to be perfectly precise.

Responses are capped at 5 MB and 10,000 records; timeouts and retries are bounded, and only
408/429/5xx and transport errors retry. Exact repeated provider IDs are retained once per
collection. Similar events and syndicated cross-source reports are not merged.

## CAST predictive signals (v0.0.3)

CAST is a short-term predictive source and always uses `ForecastSignal`, never `Event`. Because no
authoritative live contract was verified, its operator adapter uses the same internal field shape
shown for VIEWS above under the distinct `geointel-cast-adapter-v1` schema and `CAST` provider.
This reuse is a GEOINTEL adapter convention, not a claim that CAST and VIEWS publish equal schemas.
Predictions retain provider-native units and scale and are never called probabilities unless a
future reviewed source contract explicitly supplies that meaning.

Both new connectors are disabled by default. Current documentation, access/authentication,
licensing, pagination, official fields, and any credentials require human verification before
live use. Credentials must remain environment-only and must not appear in URLs, provenance,
errors, or logs.

## Alignment and disagreement

ACLED records from zero through 90 days before retrieval are `current_window`; older ones are
`historical`, and future dates are temporal mismatches. This documented inclusive threshold only
organizes context. Country mismatches, non-country predictive units, and requested/provider
horizon differences are surfaced as disagreements without aggregation. Reasoning preserves each
source independently; there is no ensemble weighting or automatic corroboration.

## Operator-provided strategic knowledge (v0.0.4)

This is an analytical source class, not a current-data connector. GEOINTEL accepts only local,
operator-provided `geointel-knowledge-v1` JSON through the controlled ingestion interface. It does
not fetch, scrape, or bundle books. Required work/section/claim/case provenance and explicit author
attribution survive retrieval. Fixtures are short original synthetic paraphrases, not excerpts.
Operators are responsible for lawful access, copyright, licensing, and accurate bibliography.

Retrieval uses deterministic concept, author/lens, historical-case, actor/geography, conflict-term,
and question-token matching with stable ordering. This is lexical/structured retrieval, not
semantic embeddings. Vector retrieval may later implement the same provenance-bearing abstraction.

## v0.1.1 provider hardening

The operational provider registry, explicit adapter-only verification state, strict normalization,
secret-safe bounded transport, failure taxonomy, and partial collection audit are specified in
[PROVIDERS.md](PROVIDERS.md). Provider health remains operational metadata, not evidence; no
unverified upstream API behavior may be inferred.

# Current news / OSINT

GDELT DOC 2.0 is used only as a broad, current-news discovery sensor. Its ArticleList records are
stored as `NewsReport`, never automatically as `Evidence`, `Event`, `Indicator`,
`ForecastSignal`, or `Forecast`. The underlying publisher remains distinct from GDELT as the
discovery provider. Exact URL deduplication does not establish publisher independence;
publication volume is not event frequency or conflict probability, and publication time is not an
event date. See [PROVIDERS.md](PROVIDERS.md) for the bounded contract and operational controls.

## Reporting sources

NewsAPI and GDELT are discovery/reporting sources, not event truth. GDELT remains `PARTIALLY_VERIFIED` following persistent live HTTP 429 observations. NewsAPI is `PARTIALLY_VERIFIED`: its official contract and operator connectivity were tested, while Developer access is development-only (100 requests/day), delayed 24 hours, and limited to roughly one month. Cross-provider copies of the same Reuters/AP/AFP or canonical article are one reporting chain, not independent confirmations. Publication time is not occurrence time.

### v0.1.5 reporting provenance

Story analysis preserves discovery provider separately from publisher/domain, author/byline, named
wire/upstream, and an optional affirmatively assigned reporting-chain ID. Missing attribution is
`UNKNOWN`; absence of a shared marker never proves independence. Cross-provider canonical copies are
one artifact, and different URLs/domains may be syndicated. Clustering never fetches article URLs.
All news fields remain untrusted inert input; credentials never enter story metadata.


## NewsAPI query intelligence

NewsAPI is unconfirmed discovery, never an event truth source. Developer access is delayed and for development/testing only. Deterministic query packs are bounded by configured global request and record limits and serialize their plan/version/families without credentials or raw responses. `X-Api-Key` remains a header; keys never enter URLs, logs, or AnalysisRun metadata. The connector does not fetch article bodies or follow article URLs.
