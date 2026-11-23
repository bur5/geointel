# Early Warning v1

Use `geointel.early_warning.evaluate` to produce an advisory record for one geographic unit,
conflict target, forecast horizon, and roster of expected source streams. The function takes an
explicit observation period end and as-of date, returns a JSON-ready snapshot and next state, and
performs no I/O. Levels describe rule outcomes. They carry no calibrated probability or validated
predictive interpretation.

## Input contract

- Declare one stream per predictive model. Use a stable series identity for a reviewed combination
  of model version, forecast question and target definition, or event source and event-type filter.
  Start a new series if those definitions change.
- Supply one observation per stream at each expected cadence boundary, weekly by default. Forecast
  observations represent issue dates. Activity observations count unique source IDs in contiguous,
  equal-length periods ending on those dates. A zero count requires affirmative coverage evidence.
- Normalize to a common geographic identity, target definition and rolling horizon before calling
  the engine. Geography compares both unit and identifier. Forecast horizons compare in months.
  With multiple models, each issue date also requires identical explicit target start/end dates
  across models. Comparability of rolling window construction across issue dates remains a caller
  responsibility.
- Use the actual availability date for as-of replay. Exact duplicate observations collapse.
  Competing records for the same stream and date make the slot ambiguous. Future-available records
  are ignored. Any missing, invalid, incompatible, ambiguous or stale required input yields
  `INSUFFICIENT_DATA`, even when another stream is complete. Unconfigured streams and dates
  outside the requested window are ignored.

`geointel.early_warning_inputs` provides read-only mappings for stored GEOINTEL `Forecast`,
`ForecastSignal` and ACLED `Event` rows. The first uses an interval midpoint, preserves its
forecast record ID, and requires the caller to establish that complete runs and questions are
comparable. Unquantified forecasts produce a missing value. This mapping supplies no target dates.
The second requires upstream alignment and an explicitly reviewed probability fraction represented
by `unit="probability"` and `scale="0-1"`. The caller supplies the model identity, including any
relevant version. Native event counts and other provider scales have no implicit conversion.
Event counts require a caller-supplied coverage record ID for a complete ACLED window. Preserve
that record and its constituent event IDs for audit, and only pass empty input when coverage has
been established. The ACLED and GEOINTEL forecast adapters use the reviewed country mapping.

## Provisional thresholds

These defaults are conservative starting heuristics. They have no scientific validation.

| Rule | Default |
| --- | --- |
| Required history | 4 consecutive observations for every expected stream |
| Freshness | Evaluation no more than 7 days after the latest scheduled period end |
| Forecast jump | At least 15 percentage points since the prior observation |
| Sustained deterioration | At least 12 points from first to latest, with every step at least 2 points |
| Activity surge | At least 5 more events and at least twice the preceding count |
| Emerging risk | All earlier values at most 5%, with the latest at least 12% |
| Model disagreement | At least 25 points between highest and lowest aligned current forecasts |
| Recovery | 2 consecutive complete evaluations with the same lower candidate |

`NORMAL` means the complete window had no qualifying signal. `WATCH` covers emerging risk or
model disagreement alone. `WARNING` requires a forecast jump, sustained deterioration, or an
activity surge. `CRITICAL` requires an activity surge together with a forecast jump or sustained
deterioration, in the absence of qualifying model disagreement in the input roster.

Escalation takes effect immediately. A downgrade requires distinct consecutive scheduled
evaluations. An insufficient-data interval resets recovery progress while retaining the prior
advisory level in state. The snapshot still reports `INSUFFICIENT_DATA` during the gap and shows
the held evidence when a later complete window is waiting for recovery confirmation.

## Machine-readable output and integration

Records include the region, target, forecast horizon, period bounds, applied thresholds, level,
candidate level, evidence with baseline/current values and source/series/record references, data
freshness and per-slot completeness, and an explanation. All snapshots are advisory. A transition to
`WATCH`, `WARNING` or `CRITICAL` produces a deterministic `event_id`, including downward
transitions that remain elevated. A continuing advisory at the same level produces no new event.
When replaying from the same initial state, identical transitions have identical IDs.

A future integration needs a read path to select point-in-time forecasts, verified complete event
windows, stable mappings for comparable targets and versions, and durable chronological state
per scope and policy. Apply state updates and idempotent inserts keyed by `event_id` together.
Display the advisory evidence, freshness, and insufficient-data status alongside any dashboard or
assistant summaries. Schedule and presentation decisions belong to the integration.

Reporting bursts, delayed batches, coverage changes, event classification shifts, and real or
apparent model revisions can trigger false positives. Forecasts that incorporate the same event
feed can produce correlated signals. Fixed thresholds can miss slow or context-specific escalation
and delayed sources can prevent classification. Midpoints hide changes in interval width. Tests
exercise synthetic inputs and deterministic rule behavior. Real-world evaluation still requires
historical point-in-time replay with coverage, lead-time and false-positive measurement.
