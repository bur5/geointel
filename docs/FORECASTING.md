# Forecasting contract

Every completed run contains exactly one assessment for interstate armed conflict, internal armed conflict, one-sided violence, and major political violence. Each contains confidence, evidence for/against, unknowns, resolution criteria, and material-change conditions. Numeric ranges are optional and require calibrated justification; merely receiving a numeric VIEWS prediction never creates a GEOINTEL probability.

The semantic boundaries are mandatory:

- **Evidence** is a retrieved historical/observed provider artifact.
- **Event** is a separately normalized real-world claim and is never auto-created by a connector.
- **Forecast signal** is an external model output with provider-native semantics.
- **Indicator** is an observed or derived variable.
- **Scenario** is a possible development.
- **Forecast** is GEOINTEL's time-bounded judgment and is immutable.

Reasoning receives observed evidence, VIEWS predictive signals, connector outcomes, missing sources, and alignment disagreements in separate fields. v0.0.3 does not average, calibrate, aggregate, or weight them. The Red Team explicitly challenges unsupported VIEWS signals, history/model inconsistency, insufficient data, unjustified extrapolation, geographic/horizon mismatch, and mistaking model output for fact. Synthesis must name every incorporated critique.

The deterministic offline provider demonstrates epistemic restraint rather than a Spain conclusion. With no validated base rates or live inputs it emits four low-confidence unquantified assessments. Production work still needs calibration, resolution adjudication, Brier/log scoring, and backtesting.

## Operational safeguards (v0.0.3)

Analyst payloads distinguish UCDP historical evidence, ACLED recent operational reports, and
VIEWS/CAST predictive signals. Dates, provider-native values, target periods, horizons, and
alignment notes remain visible. A model prediction is never evidence, an ACLED report does not
validate a model, and agreement does not create a numeric GEOINTEL probability. The deterministic
Red Team checks predictive-as-fact errors, exact/cross-source duplication, geographic and horizon
mismatch, stale/sparse events, fatality uncertainty, causal overclaiming, sensationalism, and
low-base-rate false positives. No source has override weight.

## Strategic interpretation boundary (v0.0.4)

A strategic claim is an attributed proposition; a historical case separates factual summary from
interpretation notes; a lens output is model-generated strategic interpretation. None is an
observation, calibrated model output, base rate, causal law, or probability. The Kissinger lens
uses only retrieved claims and emits claim IDs/provenance, applicability, limitations,
counterarguments, low confidence, unsupported assumptions, and analogy mismatches. It cannot add a
probability. With no relevant claims it explicitly says the lens is not informative.

Red Team now checks authority/famous-author bias, selective retrieval, cherry-picked or mismatched
analogy, retrospective determinism, theory-as-fact, theory overriding current evidence,
unsupported causation, missing alternative theories, outdated assumptions, false precision, and
sensationalism. The Spain control remains conservative: literature or analogy alone supplies no
escalation evidence.
