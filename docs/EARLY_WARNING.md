# Early Warning Engine v1

The engine emits advisory classifications for one geography, compatible outcome, and optional
forecast horizon at a time. A warning describes a change detected in the supplied observations.
The classes carry no calibrated probability or validated prediction of future conflict. This
release has deterministic synthetic tests and no measured real-world false-alarm rate, lead time,
or predictive skill.

## Input and output

Call `geointel.early_warning.evaluate(scope, observations, period_end=..., as_of=...)` with
explicit UTC calendar dates. It returns a `WarningRecord` and the next `State`. Both support
Pydantic JSON serialization and validation. The record includes the method version, advisory
flag, scope, dates, configured thresholds, classification, previous and candidate levels, coverage,
data issues, contributing evidence, explanation, and an optional event ID. Evidence contains
baseline and current periods, values, feed identity, source record IDs, and forecast target and
horizon when applicable. A model-spread comparison uses the low and high contemporaneous
predictions as its reference and current values. Retained evidence identifies the earlier basis
for an advisory that remains in state while recovery is pending or data is insufficient.

- Declare the expected feeds in `Scope` before evaluating. Use canonical region identifiers and
  units consistently and only combine activity and forecast outcomes judged substantively relevant
  to each other. Keep an independent state per scope and threshold configuration.
- Use `Observation.from_forecast` on existing GEOINTEL `NormalizedForecastSignal` records when the
  provider declares a fractional probability for a verified target. The adapter accepts the unit
  `probability` with a missing scale or `0-1`. CAST counts, unspecified provider-native outputs,
  and unquantified GEOINTEL assessments do not furnish probability values. The engine does not
  average probability ranges or convert provider-native values. Feed identity includes the model
  version. The forecast must have been issued within the observation window and available by
  `as_of`. Changes are compared within one feed at matching month-level target lead and span.
  Cross-model comparisons require identical current target dates, metric and horizon.
- Use `Observation.from_events` on existing `NormalizedOperationalEvent` records to count one
  exact event type for one country and one source per window. Supply explicit completeness and a
  coverage record ID. Only an affirmed complete window can contribute a zero count. The adapter
  counts distinct provider record IDs and verifies country, alignment, event date, and retrieval
  date. Do not supply article counts, historical coverage summaries, or estimates from an outage.
- Provide one finalized observation per expected feed per contiguous, fixed-width window, with
  inclusive start and end dates. Process periods in order and pass the prior state on each call.
  Replay with the same input and starting state yields the same event ID. Passing the returned
  state suppresses another event at the same level. An integration should key inserts by event
  ID and persist state and records atomically so retries and concurrent workers stay consistent.
  Backfills or revisions require a deliberate replay from a prior checkpoint.

## Rules and provisional defaults

| Rule | Default |
| --- | --- |
| Window and history | Three consecutive 7-day windows per required feed |
| Freshness | Latest usable window ends at most 10 days before evaluation and current forecast targets have yet to expire |
| Forecast jump | Increase of at least 15 percentage points since prior window |
| Sustained forecast change | At least 2.5 points per step and 10 points overall |
| Emerging risk | All baseline values at most 10%, current value at least 20% |
| Forecast model disagreement | Current spread of at least 25 points, or opposite movements each at least 15 points |
| Activity jump | At least five extra events and at least twice the prior count |
| Sustained activity change | At least two extra events per step and five overall |
| Hysteresis | Two consecutive complete lower readings before reducing the level |

Thresholds are configurable, conservative starting assumptions and scientifically unvalidated.
Tune cadence to source availability. A source that issues monthly will usually produce missing
windows at the weekly default. Days are fixed-width, so calendar-month schedules need explicit
handling before deployment.

- **NORMAL** means all required data checks passed and no threshold was crossed.
- **WATCH** covers emerging risk or material model disagreement.
- **WARNING** covers a qualifying forecast or activity jump or a sustained change. Multiple
  indicators from one feed do not promote a level.
- **CRITICAL** requires a reported activity jump and a forecast jump or sustained forecast rise.
  Material disagreement among comparable models blocks this promotion.
- **INSUFFICIENT_DATA** means a required feed was missing, incomplete, stale, ambiguous, or
  incompatible. It pauses classification and resets recovery progress while preserving the prior
  level in state. Evidence from usable feeds may still appear for inspection.

An event ID appears only on an upward transition. The classification record remains available
on every evaluation. Recovery tracks consecutive lower candidate levels, so the engine can
de-escalate after the configured number of periods even if absolute risk remains high.

## Synthetic output examples

These projections omit the full evidence and provenance objects. Exampleland is fictional.

| Observation window | Synthetic inputs | Advisory |
| --- | --- | --- |
| 2026-02-01 to 2026-02-21 | One-month model forecast rose from 0.09 to 0.31 and reported battles rose from 3 to 11. Three usable observations per feed and age 0 days. | CRITICAL with an event ID |
| 2026-02-01 to 2026-02-21 | Two aligned one-month model forecasts held at 0.40 and 0.10, with complete coverage and age 0 days. | WATCH with `model_disagreement` |
| 2026-02-01 to 2026-02-21 | Required forecast feed supplied only two of three observations by the evaluation date. | INSUFFICIENT_DATA with no event ID |

## Limitations and future integration

Reporting backlogs, changes in collection scope, duplicate events with distinct provider IDs,
model drift, correlated sources, or incorrect completeness metadata can drive false positives.
Strict scope and coverage checks can also suppress real signals. A wide model spread can
reflect model differences or one persistently higher model rather than a new development.
Forecast checks assume harmonized target definitions and dates. They do not establish model
independence or calibration. Weekly changes are sensitive to cutoffs and reporting delays.
The engine detects changes relative to recent windows, so a persistently high plateau may
produce a NORMAL candidate after the initial jump leaves the window.

Before dashboard or assistant integration, define a read-only mapping from persisted
`ForecastSignal` and `Event` data, verify provider semantics and coverage, and select a stable
scope and cadence. Preserve release and retrieval dates for point-in-time evaluation. Provide
ordered state persistence, event ID deduplication, and traceable source links. Display the
advisory level, data limitations, prior level during gaps, and counterevidence together.
Evaluate alert burden, lead time, missed escalations, and sensitivity to thresholds against
time-ordered adjudicated data before considering operational use.
