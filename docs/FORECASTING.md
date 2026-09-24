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

## Validation contract (v0.0.5)

Synthetic validation exercises this same forecasting contract with `OfflineModel`; it does not substitute a validation-only forecaster. Assertions inspect category completeness, unquantified output, uncertainty, immutable persistence, evidence/signal/strategy separation, disagreement, and Red Team restraint. No case specifies an expected direction or risk label, and strategic language cannot create a forecast probability. Metamorphic fixtures change one source condition while preserving these epistemic boundaries. See [validation](VALIDATION.md).

## Monitoring contract (v0.1.0)

An alert is neither an additional forecast nor a revision. Monitoring creates a new ordinary,
immutable four-category forecast set, then compares only structured state from a compatible prior
run. Baselines, prose-only differences, strategic interpretation alone, isolated/duplicate events,
and a single source outage cannot independently produce a material security alert. Mandatory Red
Team findings are retained as alert counterevidence. See [monitoring](MONITORING.md).

## v0.1.1 provider hardening

The operational provider registry, explicit adapter-only verification state, strict normalization,
secret-safe bounded transport, failure taxonomy, and partial collection audit are specified in
[PROVIDERS.md](PROVIDERS.md). Provider health remains operational metadata, not evidence; no
unverified upstream API behavior may be inferred.

## News boundary

News reports and corroboration assessments are visible for analyst and Red Team review but never automatically create an `Event`, `Evidence`, forecast signal, indicator, or forecast. Corroborated reporting is not confirmed event truth. Article counts and news volume never increase geopolitical risk or probability. News discovery windows are independent of forecast horizons.

## v0.1.5 media-story boundary

Analyst and Red Team receive bounded story clusters and corroboration assessments alongside raw media
reports. They must distinguish reports, probable story candidates, corroborated reporting, and
validated events. Neither report nor publisher volume is a probability input. Red Team should test
false merges, syndication-as-corroboration, volume bias, unresolved dependence, ambiguous geography,
and stale/republished material. Candidate indicators remain review-only and cannot raise risk.

## v0.1.5.1 deterministic relevance boundary

Each report is assessed against the request's location, question, and horizon before cluster-level
source assessment. Explicit geographic, topic, conflict, temporal, and overall states are retained
with matched terms, reasons, uncertainty, and a method version. Negative signals remove obvious
sports, entertainment, photography, consumer-product, and routine-business noise unless genuine
conflict/security language requires cautious review. Requested query geography alone is never
proof of story geography.

Cluster relevance conservatively aggregates member states: one weak report cannot establish the
whole cluster's relevance. Candidate eligibility requires established relevance as well as the
existing affirmative independent-chain and probable-story gates. The full boundary remains:

`NewsReport` → `RelevanceAssessment` → `StoryCluster` → `Source/Reporting-Chain Assessment`
→ `Candidate Indicator` → human validation → possible Evidence/Event only through a future
explicit validation process.

Relevance does not mean truth or event confirmation; corroborated reporting does not mean a
confirmed event; a candidate indicator is not Evidence/Event; and article volume is not risk.
