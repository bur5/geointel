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

## Protest stand-in after 2020 (written 2026-11-28, before the first run)
Mass Mobilization, the truth for mass protests, ends in 2020. V-Dem's expert score of mass
mobilisation (`v2cagenmob`) is used for later years only if it reproduces Mass Mobilization:
- threshold chosen on 2000–2015 so that the stand-in flags as many country-years as Mass
  Mobilization does (no other tuning);
- checked on 2016–2020: accuracy at least 70% and Cohen's kappa at least 0.4, on countries
  that Mass Mobilization covers;
- if the check fails, protest base rates stay at 1990–2020 and the site says so.
The result of the check is logged below and printed by every daily run.

## Rules from 2026-11-28 (after the holdout was opened; Fable round 5)
Written before any run under them.

**Reference.** The primary reference for types split into onset and continuation is the event
rate given the country's last known state, from past data only: how often conflicts start
among countries at peace, how often they go on among countries at war. For other types it is
the world frequency. The old "world frequency" for onset and continuation is kept as a
reference figure only: it is an easy opponent there and overstated the gains reported until
now. Re-scoring the same forecasts against the new reference is logged as "same forecasts,
new reference".

**Intervals.** 95% bootstrap intervals resample countries and years together (world-wide
shocks such as 2020 or 2022 hit many countries in one year).

**Periods.** Variants are chosen on tuning (2000–2015) and confirmed on validation
(2016–2020). The 2021–2025 period, opened once on 2026-11-28, is now a **control**: no
variant is chosen on it; a new version must not be worse on it than the previous one beyond
the interval. One look per version, each logged; the number of looks is shown on the
Accuracy page. New clean material: each newly published UCDP year is opened once by the
protected run with the owner's approval; and monthly snapshots of the published forecasts
from December 2026 are scored forward (rule to be written before the first reading, not
before May 2027).

**Danger level.** The check uses the level that the class-A probability alone would give
(ongoing class-A conflict → 4), not the final level. The order is broken only where the
intervals of neighbouring levels do not overlap. Each level is also checked against its own
band: level 1 below 2%, level 2 2–5%, level 3 5–20% a year.

**Experiments.** At most three experiments with the model a month; each is one run with its
rule written here beforehand. Planned:
- **A. Continuation of a conflict from the world continuation rate** (or strongly shrunk to
  it). Adopted if the continuation Brier on tuning is lower than the current model's and
  validation is not worse beyond the interval.
- **B. Violence below the threshold for onset of internal conflict.** Countries at peace in
  three groups by the last known year: no deaths; 1–24 deaths in state-based fighting; 25+
  deaths in other violence (non-state, one-sided). Onset rate by group, then the current
  model within the group. Same adoption rule, on onset rows.
- **C. Rivalries for interstate war.** Two groups: a country with an active strategic
  rivalry or a deadly interstate clash in a pair within 10 years, and the rest; onset rate by
  group, no regression. Adopted if skill against the primary reference on tuning is above
  zero with its interval and validation is not worse. **Decided by the owner before the run:
  if C is not adopted, the per-country probability of interstate war is removed from the
  site** (shown instead: war ongoing or not, preparation signs, one sentence on the world
  rate, scenarios labelled as expert judgement), and the subject is not reopened until
  monthly data exist.

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
- 2026-11-27, run 2 (coup variants, tuning chooses, validation confirms). Brier skill score
  vs the world frequency, tuning / validation: world prior without groups +0.025 / +0.016;
  regime groups with prior cap 2×, 5×, 10×, 400: −0.028…−0.038 / −0.061…−0.062. The regime
  grouping added in 1.3.0 (to fix "the whole world red" for 10-year coups) makes forecasts
  worse. Run 3 adds world-prior variants with a capped prior strength, so that a country's
  own record counts more without groups.
- 2026-11-28, run 4 (coup variants; choice on tuning). Tuning / validation Brier (log score):
  1.10 groups 0.02602 (0.1163) / 0.01531 (0.0792); world prior 0.02468 / 0.01419; world prior
  cap 2× 0.02461 (0.1127) / 0.01427; **hybrid (democracies pooled, others world cap 2×)
  0.02450 (0.1079)** / 0.01418 (0.0726); offset model on world cap 2× 0.02453 (0.1096) /
  0.01397 (0.0707). By the rules the hybrid is adopted (best on tuning); it also beats 1.10 on
  validation. The offset model was close and was best on validation; it is a candidate for the
  next version, to be judged on tuning again once combined with the hybrid.
- 2026-11-28, run 5 (conflict onset: does a one-year lull count as continuation? Fable round
  4, item 5). Internal conflict, gap 0 / gap 1, Brier (log score): tuning onset 0.03200
  (0.1324) / 0.03108 (0.1331), continuation 0.17975 (0.5472) / 0.18053 (0.5467); validation
  onset 0.03177 (0.1233) / 0.03455 (0.1338), continuation 0.16608 (0.5192) / 0.19424
  (0.5756). Interstate: tuning onset equal by log score, continuation worse with gap 1;
  validation worse. Tuning is mixed and validation is clearly worse, so the rule is **not
  adopted** (gap stays 0). The high Azerbaijan onset probability is better addressed by how
  the last conflict ended (UCDP Conflict Termination), planned separately.
- 2026-11-28, run 6 (coup offset model on top of the live hybrid, L2 20 and 50). Tuning Brier
  (log score): hybrid 0.02450 (0.1079); offset on hybrid 0.02455 (0.1084), with L2 50 0.02454
  (0.1083); offset on world prior cap 2× 0.02453 (0.1096), with L2 50 0.02453 (0.1099).
  Validation: hybrid 0.01418 (0.0726), offset on hybrid 0.01401 (0.0702). The offset model
  does not beat the hybrid on tuning, so by the rules **the hybrid stays**. A trained
  correction for coups is not adopted; for coups, the base rate is as good as we know.
- 2026-11-28, run 7 (internal-conflict onset corrected by how the last conflict ended, UCDP
  Conflict Termination v4-2024; Fable round 4, item 5). Onset Brier (log score), tuning /
  validation: base rate 0.03200 (0.1324) / 0.03177 (0.1233); correction L2 20 0.03263
  (0.1324) / 0.03185 (0.1204); L2 50 0.03254 (0.1326) / 0.03174 (0.1207). Worse on tuning,
  so **not adopted**. The onset base rate stays; the cap from 1.10.0 (an onset probability
  gives at most level 3) remains the guard against "Azerbaijan 28%".
- 2026-11-28, protest stand-in check (rule above, written before the run). V-Dem
  `v2cagenmob` v16, threshold 1.62 matched to the Mass Mobilization rate on 2000–2015
  (9.4% vs 9.6% of country-years). Check 2016–2020: accuracy 79.7%, **kappa 0.27** (needed
  0.4), recall 32%, precision 48%. **Failed**: the stand-in is not used and protest base
  rates stay at 1990–2020. High accuracy here mostly reflects how rare protest years are;
  kappa shows weak agreement. Next free option: none known; the paid option (news
  candidates from GDELT, labelled by a language model, checked by hand) needs the owner's
  approval of an exact sum.
- 2026-11-28, **holdout 2021–2025 opened once** (model 1.16.0, commit abb5ab1; approved by the
  owner in the `holdout` environment; result `models/holdout/2026-11-28-abb5ab1.json` on
  risk-data). Brier skill score vs the world frequency (95% interval):
  - internal conflict onset +0.55 (+0.40…+0.72), 16 events; continuation +0.79; vs "as last
    year": onset +0.14 (−0.04…+0.31), continuation −0.05 (−0.13…+0.02);
  - interstate onset −0.00 (−0.00…+0.00), 22 events: no skill;
  - coups (hybrid) +0.024 (+0.007…+0.047), 36 events; the 1.10 grouping scored +0.027 and the
    world prior cap 2× +0.025 on these years, all within each other's intervals;
  - earthquakes +0.42, tsunami +0.36, humanitarian onset +0.41, continuation +0.80;
  - economic crisis +0.08 (+0.04…+0.12);
  - mass protests: no truth after 2020, not scored.
  Danger level: share of country-years with a war by level 1–4 = 2.1%, 1.4%, 8.1%, 87.9%;
  levels 2–4 in order, **level 1 above level 2** (5 of 239 vs 6 of 437; intervals overlap);
  level 3 from a probability 8.1% (3.3–13.0%), inside the promised 5–20%.
- 2026-11-28, **re-scoring: same forecasts, new reference** (model 1.16.0, run 46125669078;
  second look at the control period 2021–2025, approved by the owner). Brier skill score
  against the primary reference (rate for the known state; world frequency for types without
  states), tuning / validation / control, 95% intervals over countries and years:
  - internal conflict onset +0.01 (−0.11…+0.11) / **+0.21** (+0.09…+0.31) / +0.14
    (−0.12…+0.31); continuation −0.04 / **−0.25** (−0.69…−0.03) / −0.05 (−0.17…+0.04);
  - interstate onset −0.08 / +0.01 / +0.01 (−0.01…+0.01);
  - coups +0.03 / +0.02 / +0.02 (+0.00…+0.06);
  - earthquakes +0.50 / +0.50 / +0.42; tsunami +0.28 / +0.27 / +0.36;
  - economic crisis −0.07 / 0.00 / +0.08;
  - humanitarian onset +0.05 / +0.09 / +0.11; continuation +0.01 / 0.00 / +0.14;
  - mass protests +0.23 / +0.11 / no truth.
  Against the world frequency (reported until now) internal onset was +0.33 / +0.38 / +0.55
  and continuation +0.68 / +0.73 / +0.79: those gains came mostly from the easy reference.
  Danger level, rule from 2026-11-28: no order violations in any period; every level is
  inside its band in every period (control: level 1 2.1% (0.9–4.8%), level 2 1.4%
  (0.6–3.0%), level 3 8.1% (4.5–14.3%)). Onset repeats caused by the two-year lag: internal
  27 of 90 / 13 of 34 / 5 of 16; interstate 2 of 14 / 2 of 7 / 9 of 22 (lists in
  `docs/onset-lists.md`). Wars at levels 1–2 in the control period: Benin and Togo 2022–23
  (spillover from the Sahel), the UK and USA 2024–25 (strikes in Yemen), Kyrgyzstan 2021–22,
  Cambodia 2025.
