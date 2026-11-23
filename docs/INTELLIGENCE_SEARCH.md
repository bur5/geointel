# Intelligence Search v1

Use `geointel.search.IntelligenceSearch` with a SQLAlchemy session and a validated
`SearchQuery`. Search reads persisted GEOINTEL records and works offline. Use a
session without pending writes. The Python API returns a `SearchPage` with
`model_dump(mode="json")` and `model_dump_json()` for serialization.

```python
from datetime import date

from geointel.search import IntelligenceSearch, RecordType, SearchQuery

page = IntelligenceSearch(session).search(
    SearchQuery(
        text='"diplomatic truce"',
        geography=("Testland",),
        sources=("Archive A",),
        record_types=(RecordType.EVIDENCE,),
        cutoff=date(2020, 1, 4),
        limit=5,
    )
)
```

Selected fields from the synthetic test corpus at that cutoff:

```json
{
  "complete": true,
  "total_matches": 1,
  "next_offset": null,
  "results": [
    {
      "record_id": "evidence:Archive%20A::abc",
      "record_type": "evidence",
      "title": "Diplomatic truce",
      "sources": ["Archive A"],
      "observed_from": "2020-01-02T00:00:00Z",
      "published_at": null,
      "retrieved_at": "2020-01-03T00:00:00Z",
      "ingested_at": "2020-01-03T00:00:00Z",
      "historical_availability": "established",
      "relevance_score": 13,
      "ranking_reasons": ["title term: diplomatic", "title term: truce", "exact query phrase"]
    }
  ]
}
```

## Query semantics

- Search is case-insensitive and Unicode-aware. All terms must match across the title,
  excerpt, or structured actor and geography labels. Exact title terms score 4,
  exact terms elsewhere score 2, and substring matches score 1. Contiguous matches
  of the full multi-term query within a single field score 5 more. Double quotes
  require a contiguous whole-token phrase. Punctuation separates tokens.
- Empty text supports browsing and filters. Geography, actor, source, and record-type
  filters combine with AND across filter fields and OR within each field. Names are
  exact after whitespace and case normalization.
- Date ranges are inclusive. The filter uses the observed period when present,
  publication for publication-only records, the issue date for external signals, and
  generation for GEOINTEL output. Work publication years match at year precision.
  Forecast target dates are available as metadata.
- Sort order is descending relevance, record type, and stable ID. Offset pagination
  is repeatable on the same corpus snapshot. For long-lived views, callers need a
  consistent snapshot across requests.
- Source-backed copies with the same record type, provider, dataset (where supplied),
  and source record ID collapse to one hit. Search chooses the latest eligible copy
  before filtering and ranking. The response carries the selected database row ID.
  Separate providers and record types remain distinct even when they describe the same
  incident. A duplicate can also reflect a revised provider record. Cross-provider
  equivalence and independence require separate evidence.

## Filters and coverage

| Record types | Structured geography and actors | Date used in range filter |
| --- | --- | --- |
| Strategic concept | Unavailable | Unavailable |
| Historical case | Recorded geography and actors | Case interval, or sole recorded endpoint |
| Knowledge work, section, strategic claim | Unavailable | Work publication year |
| Strategic analysis | Analysis run location name and ISO code | Lens analysis time |
| Evidence | Explicit country in source provenance | Observation period or publication time |
| Event | Normalized country, administrative areas and locality, primary and associated actors | Occurrence time |
| External forecast signal | Provider's source location | Issue date |
| GEOINTEL forecast | Analysis run location name and ISO code | Run completion time |

Geography covers recorded labels. Radius, polygon, alias expansion, and inferred
geography are unsupported. Search does not assign a provider observation to the
requested run location. Claim associations with historical cases do not assign the
cases' actors and geography to the claim. Source names use persisted provider or
source labels, bibliographic attribution, or the generating lens. Missing required
filter metadata excludes a hit. Inspect results without that filter for
`missing_metadata`, which identifies unknown fields. Zero matches describe the
searched corpus under the supplied query.

## Historical availability

A cutoff is inclusive through the end of its UTC day. Search checks the selected
record's persisted ingestion timestamp and checks applicable parent-ingestion,
publication, retrieval, update, observation, issue, and generation timestamps.
A timestamp after the cutoff excludes the row before deduplication and ranking.
A future forecast target is valid when the forecast itself was available. Timestamps
are also returned for freshness assessment. Source coverage freshness and latency
remain unknown unless supported by the stored metadata.

Strict mode is the default for cutoff queries. A work with only a publication year
can have unknown availability during that year. Cases without an end date, legacy
events lacking occurrence or retrieval metadata, and generated or predictive
records lacking required timestamps can also be unknown. Permissive mode includes
these rows with `historical_availability: "unknown"`. Use established results for
historical evaluation. The check uses timestamps on existing rows. Reconstructing
overwritten or deleted content requires versioned snapshots.

## Safety, limits, and downstream integration

- The code executes fixed ORM reads with bound row limits. The text query and
  filters are evaluated as data in Python. No commands, model calls, URL fetches,
  provider calls, or write operations run as part of search.
- The result projects explicit evidence and citation fields. It omits raw provider
  payloads and run configuration, strips URL credentials, query strings and
  fragments, and uses the repository's text sanitizer. Index only records
  approved for the caller's use. Source excerpts and citation text remain untrusted.
- Queries allow up to 300 characters and 20 terms, with at most 100 hits per page.
  The lexical scan is limited to 10,000 stored rows per selected record type.
  A read failure or a scan exceeding the cap produces a per-type status and marks
  the page incomplete. `total_matches` then covers only successfully read record
  types. A successful read establishes database availability for that type.
- Before assistant or briefing integration, provide a corpus authorized for the
  caller, turn record IDs and provenance into citations, and preserve record type,
  metadata gaps and historical availability. Treat retrieved text as inert content
  and relevance as a lexical ranking. For larger corpora, add a bounded index and
  snapshot-aware paging. Historical replay after source corrections requires
  immutable record versions or dated snapshots.
