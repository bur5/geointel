# Dashboard API v1

Start the read-only app with `uvicorn geointel.api.app:dashboard_app`. Its OpenAPI schema is at
`/openapi.json`, with interactive documentation at `/docs`. For dashboard deployments, route the
frontend to this entry point. The existing `geointel.api.app:app` entry point also registers the
dashboard router for internal use and continues to serve the legacy analysis and forecast routes.

The dashboard app has only read routes and has no application-level authentication. Internal routes
such as `/analysis`, `/providers`, and the legacy `/forecasts` are absent from this entry point
and return 404. Use an authenticated gateway where access control is required, and supply a database
role with read access to the relevant tables. The API reads stored records and makes zero provider
or model calls. API schemas omit internal configuration, arbitrary metadata, raw provider payloads,
and source URLs.

## Routes

All paths have the prefix `/api/v1/dashboard`.

| GET path | Response |
| --- | --- |
| `/overview` | Latest stored point and coverage for each series across stored geographies or within a filter. |
| `/countries/{country}` | The overview for one ISO country. |
| `/regions/{region}` | Side-by-side country overviews for the supported cohort in the region, ordered by ISO alpha-3. |
| `/coverage` | Availability, latest record timestamp and country-ID availability for each series. |
| `/observations` | Reported operational event records. Date bounds apply to occurrence. |
| `/ucdp-observations` | Stored UCDP GED historical and Candidate observations. Date bounds apply to occurrence start. |
| `/indicators` | Stored indicator points in their original units. Date bounds apply to observation. |
| `/forecasts` | Stored external model outputs. Date bounds apply to issuance. Target periods and horizons are included. |
| `/assessments` | Completed GEOINTEL assessments, with storage time as issuance and the original horizon, confidence, and probability bounds. |

`/overview`, `/coverage`, and all list routes accept `country` and `region`. Country filters use
case-insensitive ISO 3166-1 alpha-2 or alpha-3. Responses use alpha-3. Valid codes with no matching
records yield an empty series. Where a country code is missing, exact country names and reviewed
aliases can supply it. Operational events prefer the provider country and use the stored event
location when the provider country is absent. UCDP observations and external forecasts use source
geography. UCDP records without a country name may use the reviewed Gleditsch–Ward code mapping. Country filters only match forecasts issued for a country unit. Analysis assessments use
the analysis location. Unresolved country codes remain null, and unscoped reads retain those
records. A region filter selects only the listed cohort:

| Region | Country codes |
| --- | --- |
| `eastern-asia` | TWN |
| `southern-europe` | ESP, SRB |
| `western-africa` | NGA |
| `western-asia` | GEO |

List routes accept `start` (inclusive UTC calendar date), `end` (exclusive UTC calendar date),
`limit` (1–200, default 50), and `offset` (0–10,000, default 0). Ordering is timestamp descending,
with undated records last and UUID ascending for ties. Either date bound excludes undated rows.
Follow `next_offset` until it is null. At the offset cap, narrow the date window to retrieve
additional history. The API treats stored naive timestamps as UTC. Offset pagination reads current data, so concurrent inserts can shift
records between requests. A first page with no matches is `missing`; an empty nonzero offset
is `end_of_results`. Invalid filters return 422. Unavailable database connections return 503
with a generic message.

## Coverage and interpretation

- The overview samples the latest point in each series. There is no comparable global or regional
  risk score, country ranking, rolled-up regional risk value, or statistical estimate of geographic
  coverage in the current data.
- Freshness uses the last occurrence or observation timestamp for observations and indicators and
  the issuance timestamp for forecasts and assessments. The display cutoff is 90 days. A missing
  or future timestamp yields `unknown`. This is record recency. The API does not infer provider
  latency, publication cadence, dataset completeness, or absence of conflict from these fields.
  UCDP coverage dates, when stored, are exposed on the corresponding observation. Forecast
  `target_period_status` separately indicates whether its stored target period is upcoming, active,
  ended, or invalid.
- Events can repeat across runs or providers. Country-series counts, regional totals and rates,
  complete multi-provider incidence trajectories, and automatic cross-provider deduplication are
  unavailable. UCDP reported fatality ranges describe historical reports. Forecast probabilities
  and qualitative confidence are exposed only as stored, and provider prediction values keep
  their original target, unit, scale, and model version.
- Indicator rows may be sparse because the analysis pipeline does not populate a standardized
  indicator time series. No normalized indicator deltas, historical country risk-score series,
  calibrated uncertainty for model signals, or regular GEOINTEL forecast trajectories are
  available from the existing schema. The assessment series contains point-in-time assessments
  from potentially different questions and horizons.
- Each list request uses one bounded query with at most 201 returned rows. The overview and
  coverage use five bounded reads, one per series. Region comparison uses at most ten reads.
  Existing indexes and schemas are reused. Sorting and normalized name and JSON filters can scan
  stored tables, especially for global or deep-offset reads. The API skips total counts and
  full-table grouping. Use narrow filters for interactive trends.

## Synthetic response examples

`GET /api/v1/dashboard/forecasts?country=ES&limit=1` with one matching record and a reference time of 2025-08-01 UTC:

```json
{
  "items": [
    {
      "id": "00000000-0000-0000-0000-000000000001",
      "kind": "model_prediction",
      "geography": {"name": "Spain", "iso3": "ESP", "region": "southern-europe", "unit": "country"},
      "provenance": {
        "provider": "Synthetic Provider",
        "source_record_id": "synthetic-country",
        "analysis_run_id": "00000000-0000-0000-0000-000000000002",
        "version": "test-1",
        "retrieved_at": "2025-06-01T00:00:00Z"
      },
      "freshness": "recent",
      "issued_at": "2025-05-15T00:00:00Z",
      "target_start": "2025-07-01T00:00:00Z",
      "target_end": "2025-09-01T00:00:00Z",
      "target_period_status": "active",
      "horizon_months": 3,
      "model": "test model",
      "target_variable": "synthetic target",
      "prediction": 2.5,
      "unit": "native event count",
      "scale": "monthly",
      "alignment_status": "aligned"
    }
  ],
  "availability": "available",
  "limit": 1,
  "offset": 0,
  "next_offset": null
}
```

`GET /api/v1/dashboard/forecasts?country=CA` with no matching records:

```json
{
  "items": [],
  "availability": "missing",
  "limit": 50,
  "offset": 0,
  "next_offset": null
}
```

## Frontend integration

See the [reconstruction and review notes](DASHBOARD_RECONSTRUCTION.md) for the adapter and
the validation database isolation blocker.

Generate types from OpenAPI and map country shapes by ISO alpha-3. Keep unmapped observations and
non-country forecasts in their own views. Label source, unit, period, and availability alongside
each series. For a provider trajectory, group by native geography, provider, model/version,
issuance, target variable, unit, and scale, then order by target period. Render gaps for missing
values and include a stale-data state. Use pagination and date filters to limit chart loads.
Serve the frontend and API through the same origin or configure cross-origin access at the gateway
if separate origins are required.
