# Strategic knowledge and retrieval

## Epistemic hierarchy

GEOINTEL distinguishes observed data (`Evidence`/`Event`), predictive provider output
(`ForecastSignal`), historical facts (`HistoricalCase.factual_summary`), attributed strategic
claims (`StrategicClaim`), lens-produced strategic interpretation (`StrategicLensOutput`), analyst
inference, and immutable final forecasts. Conversion between these categories is forbidden.

## Domain and attribution

A work stores bibliography, provenance, rights status, ingestion time, and bounded metadata. Its
ordered sections store summaries and locators rather than full chapters. Each concise claim names
its attributed author, work and section, locator when available, extraction confidence, type,
provenance, limitations, counterexamples, reusable concepts, and case links. Historical cases keep
actors, geography, dates, factual summary, outcome, provenance, and explicitly separate
interpretation notes. A claim is not proof of the author's theory or of a current-world condition.

## Ingestion and copyright

`KnowledgeIngestor` validates deterministic `geointel-knowledge-v1` JSON. Identifiers and
cross-references must be unique and valid; provenance and attribution are mandatory; lengths,
counts, file size, and allowed local root are bounded. It performs no network request. Do not ingest
full copyrighted books or substantial excerpts. Operators must use material they may lawfully
process and preferably concise paraphrases. The repository fixture is synthetic test prose.

## Retrieval

`KnowledgeRetriever` is an abstraction. v0.0.4's `LexicalKnowledgeRetriever` deterministically
filters/ranks by concepts, geography, actors, conflict category, question terms, analog, and
attributed author/lens, then orders ties by stable claim ID. Results carry the work, author, claim
ID, locator, claim/work provenance, matched concepts, case IDs, limitations, counterexamples, and
retrieval reasons. It is not embedding search and cannot claim semantic completeness. A future
PostgreSQL vector implementation can replace it without changing lens or pipeline contracts.

## Lenses and auditability

`StrategicLens.analyze(context, retrieved_knowledge)` is the generic contract and `LensRegistry`
supports future Schelling, realist, institutionalist, domestic-politics, economic, demographic, or
alternative-history implementations. `NeutralAlternativeLens` proves registration without
pretending to implement a theory.

`KissingerLens` operates only on retrieval results. It frames questions about balance/equilibrium,
durable interests, alliance constraints, diplomatic arrangements, legitimacy/order, revisionism,
off-ramps, and analogy mismatch. Output identifies claims and provenance, applicability,
limitations, counterarguments, confidence, assumptions, and case IDs, with an enforced
`strategic_interpretation_not_empirical_evidence` status. It generates no probability. Empty
retrieval says it is not informative.

Every invocation becomes a `StrategicAnalysis` tied to its `AnalysisRun`, including failures,
claim/case IDs, provenance, version, output, limitations, and timestamp. Failures are non-fatal.
Strategic context remains a separate reasoning field and cannot replace source data.

## Safety, Red Team, and limitations

Stored text is untrusted data and cannot alter prompts, tools, permissions, security rules, code,
or workflow. Red Team remains mandatory and challenges authority bias, famous-author bias,
selective retrieval, analogy selection/mismatch, retrospective determinism, theory-as-fact,
evidence override, unsupported causation, missing theories, outdated assumptions, false precision,
and escalation sensationalism.

Known limitations: retrieval is lexical, the library is operator-curated and may be incomplete or
biased, bibliography is not externally verified, extraction confidence is operator supplied, no
vector embeddings are present, and the neutral lens is not substantive. Human review remains
required.
