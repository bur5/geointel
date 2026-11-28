# Forward check: scoring published forecasts against what happened

Written 2026-11-28, before any forecast was scored (Fable round 5, 3.1 step 4 and 3.5). This
is the only check that cannot be spoiled by knowing the outcome: the forecasts are stored
before the events happen.

## What is stored
The first published forecast of each calendar month, unchanged, on the `risk-data` branch:
`forward/YYYY-MM-risk.json` (base model) and `forward/YYYY-MM-signals.json` (with news,
markets, ministries and other signs). Daily copies also stay under `history/`. The first
stored month is December 2026.

## What is scored
- **Horizon:** the 1-month probability.
- **Window:** from the publication day to the same day of the next month.
- **Events and their truth:**
  - internal and interstate conflict, onset and continuation: UCDP Candidate monthly
    events (25+ deaths in the window for onset is too high for one month; the monthly
    target is **any state-based death** in the window for a country at peace, and **any
    continuing fighting** for a country at war); the yearly UCDP release later replaces the
    Candidate data when the two disagree;
  - major earthquakes: USGS (M6.5+, as in the model);
  - tsunami: NCEI;
  - coups: Cline Center releases (scored once the year's release is out).
  Protests and political crises are scored only if a source for their truth after 2020
  passes its own check.

## Metrics and decision
- Brier skill score of the published (signals) forecast against the base forecast stored
  the same day, and of the base forecast against the primary reference (rate for the known
  state), per type, with intervals over countries and months.
- **First reading: not before 1 June 2027** (six stored months). Before it, nothing about
  signals is decided from the stored forecasts.
- Signals are kept as probability multipliers only if, at the first reading with at least
  20 events of the type, their skill over the base forecast is above zero and the interval's
  upper end is above zero; otherwise they are shown as observations without changing the
  probability. Types with fewer than 20 events wait for later readings.
- Every reading is logged in `docs/backtest-rules.md` with the stored months used.
