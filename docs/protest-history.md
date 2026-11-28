# Protest history after 2020

Written 2026-11-28, before any run. Mass Mobilization, the truth for mass protests, ends in
2020; the free V-Dem stand-in failed its check (kappa 0.27, `docs/backtest-rules.md`). Two
paths are prepared; neither has been run. The workflow is `.github/workflows/protest-history.yml`.

## Event
Country × year: at least one protest against the government with more than 10,000
participants (as in Mass Mobilization). Countries Mass Mobilization does not cover are not
scored and stay "no data".

## Path 1: Carnegie Global Protest Tracker (2017 onward)
- Only after Carnegie's written permission (the owner wrote to Carnegie on 2026-11-28;
  waiting until 12.12). No download before that.
- Size: protests with a stated size above 10,000 count; "unknown" sizes do not count.
- Check: agreement with Mass Mobilization on 2017–2020.

## Path 2: paid labelling (only with the owner's approval of an exact sum)
- Candidates: all articles in Wikipedia's "Category:<year> protests" and its subcategories,
  2016–2025 (lead section only).
- A language model (Haiku) answers from the given text only, in a fixed JSON format: country,
  year, against the government, participants over / under 10,000 / unknown, and a quote. An
  answer "over 10,000" counts only if the quote is found in the article text.
- Dry run (`max_usd = 0`) is free: it counts candidates and estimates the cost. A paid run
  stops at the cap.
- The prompt is fixed as written in the code; if it has to change, it is changed only after
  looking at 2016–2017, never at the check years.
- Check: agreement with Mass Mobilization on 2018–2019 (2020 is incomplete there).
- Deviation from the reviewer's plan: a second independent source per event is not required;
  instead the participant quote must be present in the article. Recorded here so the
  reviewer can judge it.

## Rule (both paths)
1. Automatic: accuracy ≥ 70% and Cohen's kappa ≥ 0.4 against Mass Mobilization on the check
   years, countries covered by both.
2. Hand check: a sample of 100 events (50 counted, 50 not counted; seed 20261128), checked
   by a different chat than the one that ran the labelling; at most 10 errors. Recorded in
   the result file as `hand_check: {"n": 100, "errors": k}`; 20 cases with links are shown
   to the owner.
3. Only if both pass does the model use the years after 2020 (`protest_history.usable`).
   One attempt per path; the result is logged in `docs/backtest-rules.md` either way.
