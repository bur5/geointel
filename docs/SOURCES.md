# Source and connector policy

Connectors validate untrusted data, use bounded retries/timeouts, retain provenance, and cannot execute retrieved content. Failures are stored as bounded safe messages and do not abort otherwise valid analysis. Each run reports per-connector attempted, status, success, normalized-record count, and failure reason; disabled connectors are explicit and all-source failure never masquerades as live intelligence.

## UCDP

UCDP supplies historical/conflict evidence. Its endpoint is intentionally operator-configured rather than guessed. Confirm current documentation, access terms, schema, and licensing before enabling it. A UCDP artifact is Evidence, not automatically an Event.

## VIEWS

VIEWS contributes independent machine-learning forecast signals. Network access in the implementation environment did not permit authoritative endpoint verification, so v0.0.2 deliberately ships no claimed public endpoint and no real/offline forecast values. Tests use deterministic records labelled synthetic.

An enabled deployment must provide a verified adapter endpoint. The internal `geointel-views-adapter-v1` JSON contract is an implementation boundary, **not a claim that VIEWS publishes this schema**:

```json
{"forecasts":[{"id":"provider record id","model":"model name","model_version":"version or null","geographic_unit":"country/grid/etc","location":"provider location","issue_date":"ISO-8601","target_start":"ISO-8601","target_end":"ISO-8601","horizon_months":12,"target_variable":"provider target","prediction":0.0,"unit":"provider-declared unit or null","scale":"provider-declared scale or null"}]}
```

The adapter must map official documented fields without inferring semantics. GEOINTEL stores record/model identity, geography, dates/horizon, target, prediction, units/scale, retrieval time/URL, schema marker, and alignment results. It does not call a prediction a probability unless the provider's documented unit says so—and even then it remains a provider signal, not a GEOINTEL probability.

Location mismatch, non-country resolution, and horizon mismatch are surfaced. Values are retained without aggregation. Live enablement requires human verification of current VIEWS documentation and licensing plus a reviewed field mapping; secrets, if later required, must use environment variables and must never enter provenance or logs.
