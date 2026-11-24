# Intelligence briefings

Use the read-only Python service with an existing SQLAlchemy session.

```python
from datetime import date

from geointel.briefings import BriefingRequest, BriefingType, generate_briefing

request = BriefingRequest(
    briefing_type=BriefingType.COUNTRY,
    location_ids={location_id},
    cutoff=date(2024, 6, 30),
)
briefing = generate_briefing(session, request)
json_text = briefing.to_json()
markdown_text = briefing.to_markdown()
```

[View a generated synthetic briefing](BRIEFING_EXAMPLE.md).

## Scope and time

| Type | Selection |
| --- | --- |
| Country intelligence | One GEOINTEL location ID |
| Regional security | Explicit set of location IDs defining the requested region |
| Conflict situation | Explicit location IDs and exact `conflict_id` in record provenance |
| Weekly geopolitical | Explicit location IDs and the seven calendar days ending at the cutoff for observations. Uses event date, or publication date if event date is unavailable. Forecasts and strategic context are as-of the cutoff. |
| Strategic outlook | Explicit location IDs with attributed strategic context included in the executive summary |

The cutoff includes the entire UTC calendar day. Eligibility checks the record's ingestion
timestamp and available publication, retrieval, update, and event timestamps. Forecast targets
may extend beyond the cutoff. Missing dates are preserved, and records with malformed supplied
provenance timestamps are skipped. The observation age threshold defaults to 90 days and is
configurable. Age is computed from event time. Undated observations have unknown freshness.
Year-only strategic publications become eligible at the end of their publication year.

## Evidence and attribution

JSON contains ordered sections, statement kinds, citation references, source records, dates,
and provenance. Markdown renders the same attributed statements and source catalog. For
observations the service uses `Evidence`, `Event`, and `Indicator` records directly. Actor
names require structured `actors` or `associated_actors` fields. The report flags conflicting
values for comparable indicators with the same location, name, observation timestamp and unit,
or records with an explicit common `conflict_group` and different `conflict_value` values.

Published `ForecastSignal` records retain their target windows and alignment status. Numeric
GEOINTEL assessments require a nonempty set of supporting citations and unique resolution of
every supporting and opposing citation to an eligible observation from the same analysis run.
Citation strings can be database UUIDs, catalog IDs, or unambiguous upstream record IDs.
`Scenario` records are rendered as hypothetical. Strategic claims come from completed runs'
stored retrieval links and retain their author, provenance, limitations and counterexamples.
Free-form model rationales and analysis outputs are omitted from the templates.

## Integration and limits

- Callers supply location IDs and, for conflict reports, a conflict ID. Persistent incident tags
  need upstream mapping. Conflict categories on forecasts cannot identify a specific incident.
- The generator reads the current database snapshot. Reconstructing versions of records edited in
  place or deleted requires an archived snapshot or upstream version history.
- Record provenance needs comparable keys for disagreement detection. The service does not infer
  conflicts from free text or promote media discovery records to operational evidence.
- Scenario coverage depends on stored scenario records. Missing dates, missing sections, and
  withheld assessments are surfaced in Information Gaps.
- Dashboard or PDF consumers can render schema version 1 directly. A serving layer should supply
  a consistent database snapshot and apply its own access controls and presentation escaping.
- `NarrativeProvider` defines an opt-in future extension. A consumer would need to validate any
  generated explanation's citations and display it as unverified interpretation. The generator
  performs no narrative-provider invocation, network calls, writes, or scheduling.
