# Time machine: rules for testing the model on the past (pre-registered)

_Written and committed on 2026-11-27, before any time-machine run, following the reviewer's
plan (Fable, round 4, section 4). Results are judged only by these rules. Changing them later
needs a new dated section here that says why, and the change applies to the next model version._

## What is tested on the past and what is not
| Part | On the past | Why |
|---|---|---|
| Base rates of every event type with a history | yes | the history and its publication dates are known |
| Trained models | yes, on the same data layer | replaces the separate check in `trained.py` |
| Danger level 1–5 without ministries and news | yes | built from base rates and UCDP facts |
| Regional conflict levels (UCDP GED, from 1989) | later (stage 2) | needs event coordinates by month |
| Counter signs (GDELT counts, FIRMS, exchange rates, food prices) | later (stage 2), as a lower bound | archives exist, no knowledge of the future |
| News classified by a language model, Telegram, the curated journal, intelligence statements, Metaculus | **no**, forward only from November 2026 | the model and the journal know the outcome |
| Foreign-ministry advice | later, from archives | needs Wayback / GOV.UK history |
| Scenarios such as Russia–NATO | no | one-off events |
| 5- and 10-year horizons | only indirectly | too few independent windows (see below) |

## Information set (the `as_of` layer)
- A forecast is issued on **1 January of year Y**. The model may read a record only if its
  publication date is on or before that day. All model code reads data through one function,
  `as_of(source, date)`. A test fails if model code opens files or the network directly.
- When old versions of a dataset are not available, publication dates follow these lag rules:

| Source | Data for year Y−k available on 1 January Y if |
|---|---|
| UCDP/PRIO ACD, UCDP GED | k ≥ 2 (annual release in June of the next year) |
| Cline Center coups | k ≥ 2 |
| Powell & Thyne coups | k ≥ 1 |
| Mass Mobilization | k ≥ 2 |
| V-Dem / OWID regimes | k ≥ 2 |
| World Bank, IMF | k ≥ 2 |
| USGS, NOAA NCEI, GDACS, Smithsonian GVP | k ≥ 1 |

- **Poisoned records.** The test data contain records dated in the future with absurd values,
  for example 10,000 coups in 2030. If any of them changes any forecast, the test fails.

## Targets and horizon
- Unit: country × year Y. Main horizon: **1 year** (the event happens in calendar year Y).
- Conflicts are scored separately for **onset** (not active in the last known year) and
  **continuation** (active in the last known year). The last known year is Y−2 for UCDP because
  of the lag, so the model predicts two steps ahead.
- 5 and 10 years: checked only indirectly. (1) Is the yearly risk stable — does the event rate
  in years 6–10 after the issue date match years 1–5? (2) Rolling starts each year 1990–2015,
  labelled "windows overlap, weak evidence". The site says "10-year forecasts are checked only
  indirectly".

## Periods
| Period | Years Y | Use |
|---|---|---|
| Tuning | 2000–2015 | anything may be changed |
| Validation | 2016–2020 | choosing between variants; every look is written to the log below |
| Holdout | 2021–2025 | opened **once per model version**, by a separate workflow that runs only after the owner approves it in GitHub (protected environment `holdout`) |

The model parameters are written to a file whose hash is recorded in the log before the
holdout is opened. Cases used while tuning signs (Ukraine 2014 and 2022) are reported apart,
labelled "used for tuning". Cases without war (spring 2021, Taiwan 2022, Venezuela–Guyana 2023)
are always reported next to them.

## Metrics
- For probabilities, by event type, with onset and continuation apart:
  - Brier skill score and log score against three reference forecasts: the world frequency
    from the training data, "same as the last known year", and archived ViEWS releases
    (conflicts only, from 2023);
  - calibration in 10 bins;
  - AUC-PR for rare events;
  - 95% intervals by bootstrap over countries in blocks of years (1,000 resamples).
- For the danger level (class A drivers only, without ministries and news):
  - **order:** the share of country-years with a class-A event in the next 12 months must rise
    with the level, 1 < 2 < 3 < 4;
  - **band:** for country-years at level 3 from a class-A probability, the observed rate must
    fall in the promised 5–20% band, within its 95% interval.
- For alerts, once counter signs are added: alerts per year worldwide, share followed by an
  event within 3 months, share of events caught at a fixed false-alarm rate (one false alarm per
  country every 5 years), median warning time. The acceptable false-alarm share is set here
  before that stage is run: at most 4 false alarms for every alert followed by an event.

## Decisions
- A change to the base model is adopted only if it improves the validation-period Brier score
  of the type it targets and does not make any other type worse beyond its 95% interval.
- Results, including failures, are published on the "Accuracy" page with the period they
  come from.

## Log
- 2026-11-27: rules written; no run yet.
- 2026-11-27, run 1 (model 1.10.0, tuning and validation only; holdout not opened). Validation
  2016–2020, Brier skill score vs the world frequency (95% interval):
  - internal conflict onset +0.38 (+0.28…+0.51), continuation +0.73;
  - interstate onset +0.01 (−0.04…+0.08), 7 events;
  - **coups −0.06 (−0.17…−0.01): the grouped base rate is worse than the plain world
    frequency**;
  - mass protests +0.11 (+0.03…+0.20);
  - earthquakes +0.50, tsunami +0.27;
  - economic crisis +0.00 (−0.02…+0.03);
  - humanitarian onset +0.21, continuation +0.79.
  Danger level: the share of country-years with a war rises with the level in both periods;
  level 3 from a probability gave 19.0% (12.9–25.1%) against the promised 5–20%.
