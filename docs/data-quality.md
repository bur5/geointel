# Source health and freshness

Run the monitor against a completed analysis run using the existing GEOINTEL
database configuration. It issues reads and prints a single JSON report.

```sh
python -m geointel.monitoring.quality_cli ANALYSIS_RUN_UUID \
  --as-of 2026-11-23T12:00:00Z --acled-freshness-days 14
```

Applications can call `geointel.monitoring.data_quality.source_health_report(session,
analysis_run_id, as_of=..., freshness_days=...)` with a clean SQLAlchemy session.
Pass an aware timestamp at or
after run completion. Use an explicit timestamp for reproducibility. The CLI
defaults to the current UTC time. Normalized database timestamps returned without
an offset (such as on SQLite) are interpreted in UTC.

| Source | Freshness clock | Default maximum age |
| --- | --- | --- |
| ACLED | Event occurrence | 14 days |
| VIEWS | Forecast issue | 45 days |
| CAST | Forecast issue | 45 days |
| ForecastSignal | Forecast issue across persisted signals | 45 days |

These are operator defaults for monitoring. Adjust the ACLED threshold to the
area's observation context and the forecasting thresholds to each release
cadence. Override any source with a positive whole number of days using
`--<source>-freshness-days` (lowercase source name) or the Python mapping. An age
exactly at the threshold is fresh. For forecasts, freshness uses valid records
with unexpired targets when available and otherwise describes the historical
records. Expired-only coverage is stale even if the issue date is recent.

## Report contract

The report includes `schema_version: 1`, `report_type: source_data_quality`, the
analysis run ID, `as_of`, requested geography and four entries under `sources`.
Each entry contains `status`, `freshness`, `coverage`, and `findings` (stable
diagnostic codes with counts). A null freshness timestamp or age means no
usable timestamp was established. Coverage counts describe rows within this
analysis snapshot. Usable counts include individually valid historical records
and duplicates. Use `unique_record_id_count`, `expired_target_count`, and the
findings to interpret those counts.

| Status | Meaning |
| --- | --- |
| `healthy` | A successful collection with usable, fresh coverage and no detected quality findings |
| `degraded` | Some usable coverage exists alongside a quality issue, such as duplicates or incomplete collection |
| `stale` | The newest usable record exceeds its threshold or all valid forecast targets have expired |
| `unavailable` | Collection outcome is missing, ambiguous, or unsuccessful, or there are no usable records |

The ForecastSignal entry covers the persisted forecasting layer, including
the VIEWS and CAST rows already counted in their own entries. Its freshness
threshold applies to the aggregate and other signal providers. Check its
`provider_statuses` and per-provider findings for specific failures. An
unavailable provider alongside usable providers makes aggregate status at
least degraded. Fully unavailable providers produce an unavailable aggregate.
Records with the same ID in different providers count as separate identities.

Malformed report inputs and database errors propagate to callers. The CLI
exits nonzero without emitting a health report in these cases. A successful
CLI exit means JSON was produced and callers must read each status.

## Using reports in an AI agent

Verify the report schema and match its analysis run and geography to the
task. Use health, freshness, and findings to qualify statements about data
availability. Treat empty ACLED results, an unavailable source, and a
failed or missing report as insufficient information about conflict risk.
A recorded forecast value of zero may be valid data. Risk interpretation
still requires the underlying forecast, its target and horizon, provenance,
and uncertainty. Source health carries no probability or escalation judgment
and should never trigger an action on its own.

## Scope and integration

Use a migrated database and the run ID from the existing analysis workflow.
The monitor requires no new migration, provider credentials, or scheduler.
It evaluates persisted snapshots without contacting providers. Historical
runs remain readable through existing collection metadata. Duplicate counts
only include persisted identities and duplicates reported during ingestion.
Previously filtered rows without telemetry, provider-side omissions, and
individual invalid fields on upstream-rejected records may be unobservable.
Rejections or invalid persisted fields are surfaced when available.

Geography matching uses the requested location, stored location ID, and
source country name, with the repository's reviewed aliases. Official CAST
admin1 records can establish their parent country from their native identity.
Unmapped provider-specific geographic units are flagged. The report cannot
establish country-wide completeness, verify expected release schedules, or
prove that an empty query reflects zero events.
