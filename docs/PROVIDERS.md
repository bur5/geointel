# Provider operations (v0.1.2)

Provider responses are **untrusted data**. Provider configuration, authentication, health, and
failures are operational metadata; they are never geopolitical evidence or escalation signals.
No live provider is enabled by default and CI performs no live request.

| Provider | Epistemic role | Available live mode | Contract status | Authentication |
|---|---|---|---|---|
| UCDP GED | observed/historical evidence | `OFFICIAL_API` | **VERIFIED** | UCDP access token header |
| ACLED Event | observed/reported events | `OFFICIAL_API` | **VERIFIED** | ACLED OAuth bearer token |
| ACLED CAST | predictive monthly event counts | `OFFICIAL_API` | **VERIFIED** | shared ACLED OAuth client |
| VIEWS | predictive model output | `OPERATOR_ADAPTER` | **OPERATOR_ADAPTER_REQUIRED** | adapter-defined |

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

## Explicit live connectivity diagnostics

These commands are the only operator-triggered connectivity probes:

```console
python -m geointel.providers check-live UCDP
python -m geointel.providers check-live ACLED
python -m geointel.providers check-live CAST
python -m geointel.providers check-live VIEWS
```

A probe is disabled unless its provider is explicitly enabled. It is bounded to one page, one
accepted record, and 1 MB, validates authentication/connectivity/envelope schema, creates no
analysis or alert, persists nothing, and emits a sanitized failure category. CI never invokes it.
For VIEWS it checks only the configured operator adapter; it is not a claim of official API support.

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

No migration `0008` is required. Existing analysis collection metadata records connector outcomes,
and live records already have provenance storage. Migrations `0001`–`0007` remain unchanged.
