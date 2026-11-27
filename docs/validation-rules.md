# Validation rules for trained base models (pre-registered)

_Written and committed on 2026-11-27, before the first training run. Results are judged only
by these rules; changing them later requires a new dated section explaining why._

## Event types and targets
| Type | Unit | Target (y = 1) | At risk |
|---|---|---|---|
| Coup attempt | country-year | at least one coup attempt (successful or failed) in the year, Cline Center Coup d'État Project (Powell & Thyne as fallback) | all countries |
| Internal armed conflict onset | country-year | UCDP/PRIO intrastate conflict with 25+ battle deaths located in the country in the year, and none in the previous year | countries without such conflict in the previous year |
| Mass protest | country-year | only if a protest dataset covering 1995–2020+ can be downloaded (Mass Mobilization); otherwise this type is not trained and the site says so | all countries |

Onset and continuation are never mixed: the conflict model predicts onset only.

## Features (all known before the predicted year)
Log years since the last event of the type (capped at 50), events in the last 5 years, share of
land neighbours with the event in the previous year, regime type (V-Dem Regimes of the World,
4 dummies), change of regime type in the last 3 years, electoral democracy index, log GDP per
capita, GDP growth, log inflation, infant mortality, log population. Missing values are filled
with the year's median and flagged with a missing indicator. No feature uses data from the
predicted year or later (a test enforces this).

## Model
Logistic regression with L2 penalty (λ = 1), fitted by iteratively re-weighted least squares.
Nothing else is tried for the first release, so there is no model selection to overfit.

## Validation
- Forward only: for every test year Y from 2005 to the last complete year, fit on 1995…Y−1 and
  predict Y.
- Baselines: (1) the current empirical-Bayes base-rate model refitted on data up to Y−1;
  (2) persistence — the training-set frequency of the event given the event status in Y−1.
- Main metric: Brier skill score against baseline (1). Also: log score, AUC-PR (not ROC AUC),
  calibration in 5 equal-count bins.
- Uncertainty: 95% interval of the Brier skill score by bootstrap over countries (1,000
  resamples, whole countries resampled because years of one country are dependent).
- Minimum: 50 events in the test years to claim calibration, 30 to claim discrimination; below
  30 the result is reported as "not enough data" and the model is not switched on.

## Decision
The trained model replaces the base rate for a type only if the lower end of the 95% interval
of the Brier skill score against baseline (1) is above zero and at least 30 test events exist.
The decision is recorded in `docs/model-changelog.md` with the numbers, and the owner approves
the switch.

## Log
- 2026-11-27, run 1: the optimiser diverged for internal conflict and protests (coefficients
  of ±10^12, all predictions 0) and the democracy index was read from the wrong column. These
  are bugs, not rule changes: the optimiser now uses a damped Newton step with a line search,
  and the index is read from the first value column. Rules above are unchanged; run 2 is the
  first valid result. Run 1 coups (valid): Brier skill score −0.019 (95% CI −0.032…−0.004),
  base rate kept.
- 2026-11-27, run 2 (first valid): coups BSS −0.019 (−0.032…−0.005), 99 events; internal
  conflict onset +0.035 (−0.020…+0.087), 83 events; mass protests (2005–2020 only) +0.034
  (−0.010…+0.080), 326 events. No type passes the rule; base rates stay. Protests also lack
  current data (Mass Mobilization ends in 2020).
