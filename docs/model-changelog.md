# GeoIntel model changelog

Every change that can move a published probability gets a new `MODEL_VERSION`
(`src/geointel/risk/__init__.py`), an entry here, and a before/after report.

## 1.1.0 — 2026-11-27
- Model version written into `risk.json`, `signals.json`, `scenarios.json`.
- Daily archive now also keeps `history/<date>-signals.json` (warning signs per day).
- Russian public procurement source removed (unreachable outside Russia).

## 1.0.0 — 2026-11-26
- State before the review-driven rework (base rates, warning signs, scenarios, trees).
