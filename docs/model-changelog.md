# GeoIntel model changelog

Every change that can move a published probability gets a new `MODEL_VERSION`
(`src/geointel/risk/__init__.py`), an entry here, and a before/after report.

## 1.8.0 — 2026-11-27
- Mass protests get a base-rate model: Mass Mobilization (Clark & Regan, CC0), country-years
  with a protest against the government of more than 10,000 people, 1990–2020. Countries outside
  the dataset have no estimate. The data end in 2020; the site says so. Class C in the danger
  level (can raise it to 2 at most).
- Political crisis: five-point definition published; probabilities are not computed (no history
  of sufficient quality for all countries 2000–2025). The site shows a "now" view: countries
  where the news reported a crisis event in 60 days (leader exit, early election, impeachment,
  political emergency rule, coup attempt), with the number of outlets.
- New news signs (observations, multiplier 1): leader_exit, snap_election, impeachment,
  emergency_rule, airspace_warning (EASA); migration policy changes are journalled separately.

## 1.7.0 — 2026-11-27
- Internal armed conflict onset uses ViEWS (Uppsala/PRIO, latest monthly run) as the base:
  log-odds mean with weight 0.7 for ViEWS and 0.3 for the GeoIntel model, for countries not in
  an active conflict. ViEWS gives P(25+ state-based battle deaths) per month; the 12-month
  figure lies between the highest month and the union under independence (both ends form the
  range, the point is their log-odds midpoint); 5y/10y extend it as a constant annual hazard.
  The GeoIntel-only numbers are kept (`own_horizons`) and shown beside the blend. Countries
  with an active conflict keep the continuation model; ViEWS is shown for comparison.
  Weights are fixed until there are enough resolved months to fit them (plan, stage 2).

## 1.6.0 — 2026-11-27
- Regional conflicts: UCDP GED (annual, last 3 years) and UCDP Candidate (monthly) events
  located in first-level regions. 5+ deaths in fighting or attacks in the last 90 days → level 5
  for the region; 25+ in 12 months → 4; 5+ in 12 months → 3. These feed the population-weighted
  country level and are named on the country page.
- Coups: V-Dem regime types are parsed from OWID labels (the 1.3.0 grouping was silently off).
- Trained base models (`trained.py`, monthly workflow) with pre-registered forward validation;
  a type is switched on only if it beats the base rate (95% CI of the Brier skill score > 0).
- Canada and Germany travel advice join the US and UK in the foreign-ministry median.

## 1.5.0 — 2026-11-27
- Regional layer (`regional.py`): for every first-level region, how often each natural
  hazard struck it (empirical Bayes across the country's regions), named volcanoes that erupted
  since 1900 (Smithsonian GVP), the highest recorded tsunami wave, and a current level from
  active GDACS alerts located in the region (orange 3, red 4).
- Population per region from GeoNames cities of 15,000+; a country's danger level is at least
  the population-weighted median of its regional levels, and the worst regions are named with
  the share of the population living there — a cyclone in Florida no longer paints Minnesota.
- New files: `regional.json` and light per-country region shapes `regions/<ISO3>.json`.

## 1.4.0 — 2026-11-27
- Warning signs: within a group only the strongest raising and lowering sign count (news,
  Telegram and GDELT often report one event); no single sign moves the odds more than ×10;
  the total is capped by the stage of preparation (×5 without personnel/logistics/final signs,
  ×20 at stage 2, ×100 at stage 3) instead of ×500; the ×1.5 combination bonus and the ×1.25
  persistence bonus are removed.
- Machine-classified news signs count as automated evidence (smaller caps), whatever the sign.
  The classifier must quote the headline and name the country; answers failing these rule
  checks are dropped. "Airspace" now means closures for expected military action only.
- Military aircraft (ADS-B), GPS jamming and radar changes became observations (×1) until a
  with/without test shows they help.
- Official assessments: range mid-points and several judgements are averaged in log-odds
  (the geometric mean of probabilities biased results down).
- Scenario pool: a logarithmic pool is reported next to the linear one; the range is the 90%
  interval of the component mixture with an uncertain sign factor (Monte Carlo) and contains
  both pools.
- Russia–NATO trees: year 1 is calibrated to the monthly profile shown as "1 year"; a
  sensitivity table shows how 5- and 10-year results move with each assumption, and the
  published 5/10-year ranges include these spreads.
- Data freshness: the last successful download of every source is kept across runs and shown;
  sources silent for more than 3 days are marked outdated. IODA requests are retried; Russian
  media timelines are fetched before the headline classifier so GDELT's limit is not spent.

## 1.3.0 — 2026-11-27
- Coups: countries are shrunk towards similar countries — V-Dem Regimes of the World (4 types)
  × coup or attempt in the last 20 years — instead of the world mean, which gave every country
  at least 21% over 10 years. The 10-year horizon mixes in 5% of the world rate as an
  allowance for regime change. Groups with fewer than 8 countries fall back to the world prior.

## 1.2.0 — 2026-11-27
- Absolute danger level 1–5 per country (`danger.py`), separate from the relative trend arrow.
  Severity classes A/B/C with class thresholds on the 12-month probability (1-month ×12 when
  higher); ongoing wars by UCDP intensity; country-scale natural hazards no longer raise the
  level (listed as regional); active UN appeals = level 2 until INFORM Severity is loaded.
- Foreign-ministry advice: lower median may raise the model level by one step, never lowers it;
  gaps of 2+ steps are shown; risks to foreigners listed separately.
- Travel, business and short-stay relocation verdicts are floored by the danger level, so the
  page can no longer say "normal" and "do not travel" at once.
- UCDP: the US campaign against al-Qaida (coded as intrastate, located in the USA) no longer
  counts as internal war on US soil.

## 1.1.0 — 2026-11-27
- Model version written into `risk.json`, `signals.json`, `scenarios.json`.
- Daily archive now also keeps `history/<date>-signals.json` (warning signs per day).
- Russian public procurement source removed (unreachable outside Russia).

## 1.0.0 — 2026-11-26
- State before the review-driven rework (base rates, warning signs, scenarios, trees).
