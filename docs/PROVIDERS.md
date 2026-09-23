# Provider operations (v0.1.3.1)

Provider responses are **untrusted data**. Provider configuration, authentication, health, and
failures are operational metadata; they are never geopolitical evidence or escalation signals.
No live provider is enabled by default and CI performs no live request.

| Provider | Epistemic role | Available live mode | Contract status | Authentication |
|---|---|---|---|---|
| UCDP GED | observed/historical evidence | `OFFICIAL_API` | **VERIFIED** | UCDP access token header |
| ACLED Event | observed/reported events | `OFFICIAL_API` | **VERIFIED** | ACLED OAuth bearer token |
| ACLED CAST | predictive monthly event counts | `OFFICIAL_API` | **VERIFIED** | shared ACLED OAuth client |
| VIEWS | predictive model output | `OPERATOR_ADAPTER` | **OPERATOR_ADAPTER_REQUIRED** | adapter-defined |
| GDELT DOC 2.0 | news/OSINT discovery sensor | `OFFICIAL_API` | **PARTIALLY_VERIFIED** | none |

`OFFICIAL_API`, `OPERATOR_ADAPTER`, `FIXTURE`, and `DISABLED` remain the exact integration-mode
set. `GET /providers` and `python -m geointel.providers status` report mode, configured/enabled
state, authentication configured (boolean only), verification, last collection state, and official
documentation links without exposing credential values.

## UCDP GED official API

Authoritative contract: <https://ucdp.uu.se/apidocs/>. GEOINTEL uses the official HTTPS API host,
`gedevents` resource, explicit dataset version path, `x-ucdp-access-token` header, and documented
`pagesize`/`page` parameters. It stops at `TotalPages`; malformed or changing page counts, duplicate
IDs, quota/auth errors, schema failures, response bounds, maximum pages, and maximum records are
audited. The default currently verified GED version is `26.1`, but `UCDP_DATASET_VERSION` is
explicitly configurable and is preserved in each record's provenance. GED records remain
observed/historical evidence and never become forecasts.

Request an API token from UCDP under its current access process, store it in the deployment secret
manager, then configure (values shown are placeholders):

```dotenv
UCDP_MODE=official_api
UCDP_ACCESS_TOKEN=<secret supplied by UCDP>
UCDP_DATASET_VERSION=26.1
```

The token is header-only. It is not placed in URLs, logs, provenance, database fields, registry
output, or diagnostics. The documented quota is 5,000 requests/day; `429` is classified as
`RATE_LIMITED`, not as evidence.

## ACLED Event official API and OAuth

Authoritative references: [getting started](https://acleddata.com/api-documentation/getting-started),
[Event endpoint](https://acleddata.com/api-documentation/acled-endpoint), and
[API elements/pagination](https://acleddata.com/api-documentation/elements-acleds-api).
GEOINTEL obtains an in-memory OAuth token from `https://acleddata.com/oauth/token` using the
documented password flow (`grant_type=password`, `client_id=acled`, `scope=authenticated`). It
caches the access token, tracks expiry, and uses the refresh token while valid. Neither token nor
the username/password is persisted or represented in provenance.

Obtain a myACLED account/API entitlement through ACLED, then configure secrets:

```dotenv
ACLED_MODE=official_api
ACLED_USERNAME=<myACLED account email>
ACLED_PASSWORD=<secret>
```

Events are fetched as JSON from `https://acleddata.com/api/acled/read`. Cursor pagination starts at
`0`, consumes `next_cursor`, stops on `null`, and safely aborts on repetition, malformed cursors,
page/record limits, or partial failure. Exact `event_id_cnty` identity is preserved; only exact IDs
are deduplicated. Dates, event/sub-event types, actors, administrative geography, coordinates,
source metadata, and fatalities are retained. Fatalities remain provider-reported estimates, not
certainty.

**October 1, 2026 transition:** ACLED documents that standard pagination will be deprecated for
non-monadic requests on that date. This connector already uses cursor pagination and does not
supply `page`, so it is compatible with that transition.

## CAST official API

Authoritative contract: <https://acleddata.com/api-documentation/cast-endpoint>. CAST uses the same
in-memory ACLED OAuth and hardened transport but separate normalization. `country`, `admin1`,
forecast month/year, provider timestamp, and separate `total`, `battles`, `erv`, and `vac` targets
are normalized only into `ForecastSignal` values. The unit is exactly `forecast_event_count`; a
value of `4` is neither 4%, probability `0.04`, nor a risk score. Observed columns are retained only
inside clearly named `observed_context` provenance and never substituted for forecast values.
Configure `CAST_MODE=official_api` plus the same ACLED secrets. ACLED Event and CAST remain
epistemically and structurally distinct despite their shared authentication infrastructure.

## VIEWS investigation result

The official entry points reviewed were <https://viewsforecasting.org/data>,
<https://viewsforecasting.org/source-code/>, and <https://viewsforecasting.org/user-guide/>. They
establish that VIEWS publishes country/subnational predictive products and REST API access, but the
exact current endpoint paths, request parameters, authentication, pagination, and response schema
could not be independently retrieved in this environment (the web research service returned HTTP
401). GEOINTEL therefore does **not** guess a direct contract or mark VIEWS `OFFICIAL_API`.
VIEWS retains the strict operator-adapter schema and predictive-only semantics. Processed VIEWS
inputs must never replace authoritative original-source data.

## GDELT DOC 2.0 current-news discovery

Authoritative references are the [DOC 2.0 announcement and parameter documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
and the official `https://api.gdeltproject.org/api/v2/doc/doc` endpoint. GEOINTEL uses one bounded,
read-only `ArticleList` JSON request with `query`, `mode=artlist`, `format=json`, `maxrecords`
(capped at 250), and explicit `startdatetime`/`enddatetime`. It requests a rolling 0–90 day
publication window. DOC ArticleList has no pagination contract used by this connector, so
GEOINTEL does not invent one. The connector requires no API key, is disabled by default, and its
schema identifier is `gdelt-doc2-artlist-json-v1`.

The provider query is a deterministic quoted, length-bounded location—not the user's analysis
prompt. Accepted ArticleList fields are `url`, `title`, `seendate`, `domain`, `language`, and
`sourcecountry`; unknown fields remain untrusted provider data in bounded provenance. GEOINTEL
does not fetch article URLs or scrape publishers. Exact conservatively canonicalized URLs are
deduplicated within a collection. Similar titles are **not** identity proof; cluster identity and
publisher independence remain unknown.

**Epistemic boundary:** GDELT is a discovery/news sensor. A GDELT article is not a confirmed
event, Evidence, an Indicator, a ForecastSignal, a Forecast, or independent corroboration.
Article volume is not event frequency or conflict probability. A publication timestamp is not
an event-occurrence timestamp. Query relevance does not prove geographic alignment, and an empty
response does not prove that no real-world event occurred. News may be incomplete, biased,
duplicated, syndicated, contradictory, or malicious prompt-injection text; it remains inert data.

Future work could implement an explicit, human-reviewable corroboration workflow that compares
underlying claims with independent primary or validated event sources, records contradictions,
and creates a separately attributed promotion decision. v0.1.3 intentionally implements no such
automatic promotion or independence claim.

**Operator observation (2026-09-22/23; not a permanent property of GDELT):** the official DOC
2.0 endpoint was reachable but returned HTTP 429 during repeated, bounded diagnostic attempts.
One attempt encountered a TLS handshake timeout at the default 10-second timeout. Raising the
local `GDELT_TIMEOUT_SECONDS` to 30 seconds allowed TLS connectivity, after which the endpoint
again returned HTTP 429. Successful live data and schema normalization verification therefore
remains pending; GDELT must not be described as production/live verified.

v0.1.3.1 classifies a definitive 429 as `RATE_LIMITED`, makes no follow-up GDELT request, and
returns a sanitized `retry_after_seconds` diagnostic when `Retry-After` contains decimal delay
seconds. Values are capped at 3,600 seconds; missing or malformed values become `null`. The
diagnostic does not sleep on or retry a 429, expose the response body or headers, persist records,
create alerts, or treat provider health as geopolitical evidence or operational coverage. The
timeout remains locally configurable; the default was not increased.

## Explicit live connectivity diagnostics

These commands are the only operator-triggered connectivity probes:

```console
python -m geointel.providers check-live UCDP
python -m geointel.providers check-live ACLED
python -m geointel.providers check-live CAST
python -m geointel.providers check-live VIEWS
python -m geointel.providers check-live GDELT
```

A probe is disabled unless its provider is explicitly enabled. It is bounded to one page, one
accepted record, and 1 MB, validates authentication/connectivity/envelope schema, creates no
analysis or alert, persists nothing, and emits a sanitized failure category. CI never invokes it.
For VIEWS it checks only the configured operator adapter; it is not a claim of official API support.
GDELT uses the inert deterministic connectivity location, a 90-day window, and never prints article
bodies. A successful HTTP response—especially an empty one—does not establish sufficient current
operational coverage.

## Security and failure boundaries

`HardenedTransport` requires credential-free absolute HTTPS URLs, rejects local/private/link-local
addresses unless an operator explicitly opts into a controlled private adapter, bounds timeouts,
retries and decoded response bytes, requires JSON, sanitizes URLs/errors, and disables redirects.
Thus an official host cannot redirect the client to an internal address. Deployment egress controls
must still mitigate DNS rebinding.

OAuth form secrets and bearer/UCDP headers are used only at request time. Passwords, access tokens,
refresh tokens, UCDP tokens, cookies, and authorization headers are absent from provenance and the
database. Provider error bodies are not surfaced. Fixture/provider text cannot execute
instructions: it remains validated, bounded, attributed data. Partial pages retain valid records
and operational audit metadata; outage, OAuth failure, quota exhaustion, and unavailable forecast
sources never become an observed event or escalation.

Migration `0008` additively creates `news_reports`, with per-run canonical-URL uniqueness and
bounded provider-identity/run-publication indexes. Migrations `0001`–`0007` remain unchanged.
