# Global risk snapshot (v0)

`python -m geointel.risk fetch` downloads public datasets; `python -m geointel.risk build`
produces `risk.json` (schema `geointel-risk-snapshot-v1`) for all 193 UN members plus
Kosovo, Palestine and Taiwan. The **Risk snapshot** workflow runs daily and publishes
`latest/risk.json`, `latest/manifest.json` and `history/YYYY-MM-DD.json` to the
`risk-data` branch.

## Event types and sources

| Type | Source | Question |
| --- | --- | --- |
| Internal armed conflict | UCDP/PRIO ACD (≥25 battle deaths/year) | onset within horizon, or still active at horizon end |
| Interstate armed conflict | UCDP/PRIO ACD, primary government sides | same |
| Coup attempt | Powell & Thyne | at least one attempt within horizon |
| Major earthquake (M6.5+) | USGS ComCat, place label names the country | at least one within horizon |
| Protests, political, economic, humanitarian crises | — | not yet modeled → `available: false` |

A source that fails to download or parse makes its types unavailable. It is never
treated as zero risk.

## Method

* Window: 1990 to the last complete year (state-creation years respected).
* Recency weighting: half-life 10 years (none for earthquakes).
* Empirical Bayes: each country's annual rate is shrunk towards a Beta prior fitted by
  method of moments across all countries.
* Horizons 1 month, 1 year, 5 years, 10 years. Simple events: `1 - (1 - p)^h`.
  Conflicts: two-state continuous-time Markov chain with onset (`p01`) and continuation
  (`p11`) rates; peaceful countries get P(onset within h), countries with an active
  conflict get P(still active at h).
* Intervals: 90% posterior intervals of the parameters propagated through the formulas.
* Confidence label from the 1-year interval width. Calibration status: `not_calibrated`.

This is an outside-view baseline. Current-signal adjustment (news, VIEWS, markets) and
calibration against outcomes are the next steps.

## Changes

`changes` lists probability moves of at least 2 percentage points per horizon and
question flips (peace ↔ active conflict) since the previous published snapshot.
