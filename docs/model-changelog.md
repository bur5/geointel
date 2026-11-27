# GeoIntel model changelog

Every change that can move a published probability gets a new `MODEL_VERSION`
(`src/geointel/risk/__init__.py`), an entry here, and a before/after report.

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
