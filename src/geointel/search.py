"""Offline lexical retrieval over persisted GEOINTEL evidence and context."""

import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import quote, urlsplit, urlunsplit

from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from geointel.domain.models import (
    AnalysisRun,
    Event,
    Evidence,
    Forecast,
    ForecastSignal,
    HistoricalCase,
    KnowledgeSection,
    KnowledgeWork,
    Location,
    Source,
    StrategicAnalysis,
    StrategicClaim,
    StrategicConcept,
)
from geointel.knowledge.retrieval import claims_with_work
from geointel.providers.runtime import sanitize_text

MAX_ROWS_PER_TYPE = 10_000
MAX_TEXT = 8_000
_TOKEN = re.compile(r"[^\W_]+")
FilterValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Scalar = str | bool | int


class RecordType(StrEnum):
    CONCEPT = "strategic_concept"
    CASE = "historical_case"
    CLAIM = "strategic_claim"
    ANALYSIS = "strategic_analysis"
    WORK = "knowledge_work"
    SECTION = "knowledge_section"
    EVIDENCE = "evidence"
    EVENT = "event"
    SIGNAL = "forecast_signal"
    FORECAST = "forecast"


class SearchQuery(BaseModel, frozen=True):
    text: str = Field(default="", max_length=300)
    geography: tuple[FilterValue, ...] = Field(default=(), max_length=20)
    actors: tuple[FilterValue, ...] = Field(default=(), max_length=20)
    sources: tuple[FilterValue, ...] = Field(default=(), max_length=20)
    record_types: tuple[RecordType, ...] = Field(default=(), max_length=len(RecordType))
    date_from: date | None = None
    date_to: date | None = None
    cutoff: date | None = None
    strict_historical: bool = True
    offset: int = Field(default=0, ge=0, le=100_000)
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        if self.text.strip() and not _TOKEN.search(self.text):
            raise ValueError("search text must contain a letter or number")
        if len(_TOKEN.findall(self.text)) > 20:
            raise ValueError("search text must contain at most 20 terms")
        return self


class Provenance(BaseModel):
    stored_record_id: str
    source_record_id: str | None = None
    parent_record_id: str | None = None
    locator: str | None = None
    url: str | None = None
    source_metadata: dict[str, Scalar] = Field(default_factory=dict)
    record_metadata: dict[str, Scalar] = Field(default_factory=dict)
    cited_claim_ids: tuple[str, ...] = ()
    cited_case_ids: tuple[str, ...] = ()


class SearchResult(BaseModel):
    record_id: str
    record_type: RecordType
    title: str
    excerpt: str
    sources: tuple[str, ...] = ()
    provenance: Provenance
    geography: tuple[str, ...] = ()
    actors: tuple[str, ...] = ()
    published_at: datetime | None = None
    publication_year: int | None = None
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    issued_at: datetime | None = None
    generated_at: datetime | None = None
    target_start: datetime | None = None
    target_end: datetime | None = None
    horizon_months: int | None = None
    prediction: float | None = None
    prediction_unit: str | None = None
    probability_low: float | None = None
    probability_high: float | None = None
    retrieved_at: datetime | None = None
    ingested_at: datetime
    parent_ingested_at: datetime | None = None
    updated_at: datetime | None = None
    historical_availability: Literal["not_requested", "established", "unknown"] = "not_requested"
    relevance_score: int = 0
    ranking_reasons: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    missing_metadata: tuple[str, ...] = ()


class SourceStatus(BaseModel):
    record_type: RecordType
    status: Literal["available", "unavailable", "scan_limit_exceeded"]


class SearchPage(BaseModel):
    results: list[SearchResult]
    sources: list[SourceStatus]
    total_matches: int
    offset: int
    next_offset: int | None
    complete: bool


def _strings(*values: object, limit: int = 200) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            sanitize_text(value, limit)
            for value in values
            if isinstance(value, str) and value.strip()
        )
    )


def _list(value: object, limit: int = 200) -> tuple[str, ...]:
    return _strings(*value[:100], limit=limit) if isinstance(value, list) else ()


def _text_list(value: object) -> str:
    return " ".join(_list(value, limit=500))[:MAX_TEXT]


def _mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _metadata(value: object) -> dict[str, Scalar]:
    value = _mapping(value)
    # Only project documented citation fields. Arbitrary JSON can contain private configuration.
    keys = (
        "provider",
        "dataset",
        "dataset_version",
        "record_id",
        "temporal_role",
        "coverage_semantics",
        "source_name",
        "source",
        "schema",
        "publisher",
        "citation",
        "fixture",
        "paraphrase",
        "not_a_book_excerpt",
    )
    return {
        key: sanitize_text(value[key]) if isinstance(value[key], str) else value[key]
        for key in keys
        if key in value and isinstance(value[key], (str, int, bool))
    }


def _source(metadata: dict) -> tuple[str, ...]:
    return _strings(
        *(
            metadata.get(key)
            for key in ("provider", "source_name", "source", "publisher", "dataset")
        )
    )


def _url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 2_000:
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme in {"http", "https"} and parts.hostname:
            netloc = parts.netloc.rsplit("@", 1)[-1]
            return sanitize_text(urlunsplit((parts.scheme, netloc, parts.path, "", "")), 2_000)
    except ValueError:
        return None
    return None


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _result(
    kind: RecordType,
    row,
    identity: tuple[str, ...],
    title: str,
    text: str,
    *,
    provenance: Provenance | None = None,
    **fields,
) -> SearchResult:
    return SearchResult(
        record_type=kind,
        record_id=":".join((kind, *(quote(part, safe="") for part in identity))),
        title=sanitize_text(title, 500),
        excerpt=sanitize_text(text, MAX_TEXT),
        ingested_at=max(_timestamp(row.created_at), _timestamp(row.ingested_at))
        if kind == RecordType.WORK
        else _timestamp(row.created_at),
        provenance=provenance or Provenance(stored_record_id=str(row.id)),
        **fields,
    )


def _work_record(kind: RecordType, row, work: KnowledgeWork, identity, title, text, **fields):
    source_metadata = _metadata(work.source_provenance)
    record_metadata = _metadata(getattr(row, "provenance", None))
    year = work.publication_year
    return _result(
        kind,
        row,
        identity,
        title,
        text,
        sources=_strings(*_source(source_metadata), work.author, work.publisher),
        publication_year=year if year and 1 <= year <= 9999 else None,
        parent_ingested_at=max(_timestamp(work.ingested_at), _timestamp(work.created_at))
        if row is not work
        else None,
        provenance=Provenance(
            stored_record_id=str(row.id),
            parent_record_id=work.external_id if row is not work else None,
            locator=sanitize_text(row.locator) if getattr(row, "locator", None) else None,
            url=_url(_mapping(work.source_provenance).get("url")),
            source_metadata=source_metadata,
            record_metadata=record_metadata,
        ),
        **fields,
    )


def _work(row: KnowledgeWork):
    return _work_record(
        RecordType.WORK,
        row,
        row,
        (row.external_id,),
        row.title,
        " ".join(_strings(row.author, row.publisher, row.edition)),
        limitations=("Bibliographic context.",),
    )


def _section(row: KnowledgeSection):
    return _work_record(
        RecordType.SECTION,
        row,
        row.work,
        (row.work.external_id, row.section_identifier),
        row.title,
        row.summary,
        limitations=("Attributed summary.",),
    )


def _claim(row: StrategicClaim):
    return _work_record(
        RecordType.CLAIM,
        row,
        row.work,
        (row.external_id,),
        row.attributed_author,
        row.claim_text,
        limitations=("Attributed strategic proposition.", *_list(row.limitations, limit=500)),
    )


def _concept(row: StrategicConcept):
    metadata = _metadata(row.provenance)
    return _result(
        RecordType.CONCEPT,
        row,
        (row.slug,),
        row.name,
        row.description,
        sources=_source(metadata),
        provenance=Provenance(
            stored_record_id=str(row.id),
            record_metadata=metadata,
            url=_url(_mapping(row.provenance).get("url")),
        ),
        limitations=("Strategic concept.",),
    )


def _case(row: HistoricalCase):
    metadata = _metadata(row.source_provenance)
    return _result(
        RecordType.CASE,
        row,
        (row.external_id,),
        row.name,
        row.factual_summary,
        sources=_source(metadata),
        geography=_list(row.geography),
        actors=_list(row.actors),
        observed_from=_timestamp(row.start_date),
        observed_to=_timestamp(row.end_date),
        provenance=Provenance(
            stored_record_id=str(row.id),
            record_metadata=metadata,
            url=_url(_mapping(row.source_provenance).get("url")),
        ),
        limitations=("Historical context with no inference about current conditions.",),
    )


def _provider_record(kind, row, provider, title, text, facts, *, url=None, **fields):
    metadata = _metadata(facts)
    source_id = row.source_record_id
    # Dataset separates distinct source namespaces (e.g. UCDP GED and GED Candidate).
    dataset = metadata.get("dataset")
    identity = (
        (provider, str(dataset or ""), source_id) if provider and source_id else (str(row.id),)
    )
    return _result(
        kind,
        row,
        identity,
        title,
        text,
        sources=_strings(provider, *_source(metadata)),
        provenance=Provenance(
            stored_record_id=str(row.id),
            source_record_id=source_id,
            url=_url(url),
            record_metadata=metadata,
        ),
        **fields,
    )


def _evidence(row: Evidence, provider: str):
    facts = _mapping(row.provenance)
    return _provider_record(
        RecordType.EVIDENCE,
        row,
        provider,
        row.title,
        row.summary,
        facts,
        url=row.url,
        geography=_strings(facts.get("country")),
        published_at=_timestamp(row.published_at),
        observed_from=_timestamp(row.event_date),
        observed_to=_timestamp(facts.get("date_end")),
        retrieved_at=_timestamp(row.retrieved_at),
        limitations=("Persisted source evidence. Inspect source coverage and reporting limits.",),
    )


def _event(row: Event, provider: str | None):
    facts = _mapping(row.provenance)
    return _provider_record(
        RecordType.EVENT,
        row,
        provider,
        row.event_type,
        row.description,
        facts.get("provenance"),
        url=facts.get("source_url"),
        geography=_strings(
            *(facts.get(key) for key in ("country", "admin1", "admin2", "admin3", "locality"))
        ),
        actors=_strings(*_list(facts.get("actors")), *_list(facts.get("associated_actors"))),
        observed_from=_timestamp(row.occurred_at),
        retrieved_at=_timestamp(facts.get("retrieved_at")),
        updated_at=_timestamp(facts.get("updated_at")),
        limitations=("Reported observation.", *_list(facts.get("alignment_notes"), limit=500)),
    )


def _signal(row: ForecastSignal):
    return _provider_record(
        RecordType.SIGNAL,
        row,
        row.provider,
        row.model_name,
        row.target_variable,
        row.provenance,
        url=row.source_url,
        geography=_strings(row.source_location),
        issued_at=_timestamp(row.issue_date),
        retrieved_at=_timestamp(row.retrieved_at),
        target_start=_timestamp(row.target_start),
        target_end=_timestamp(row.target_end),
        horizon_months=row.horizon_months,
        prediction=row.prediction,
        prediction_unit=sanitize_text(row.unit) if row.unit else None,
        limitations=("External predictive signal.", *_list(row.alignment_notes, limit=500)),
    )


def _analysis(row: StrategicAnalysis):
    return _result(
        RecordType.ANALYSIS,
        row,
        (str(row.id),),
        row.lens_name,
        _text_list(_mapping(row.output).get("interpretation")),
        sources=_strings(row.lens_name),
        generated_at=_timestamp(row.analyzed_at),
        geography=_run_geography(row.analysis_run),
        provenance=Provenance(
            stored_record_id=str(row.id),
            parent_record_id=str(row.analysis_run_id),
            record_metadata={"lens_version": row.lens_version},
            cited_claim_ids=_list(row.retrieved_claim_ids),
            cited_case_ids=_list(row.retrieved_case_ids),
        ),
        limitations=("Generated strategic interpretation.", *_list(row.limitations, limit=500)),
    )


def _run_geography(run: AnalysisRun) -> tuple[str, ...]:
    return _strings(run.location.name, run.location.iso_code) if run.location else ()


def _forecast(row: Forecast):
    return _result(
        RecordType.FORECAST,
        row,
        (str(row.id),),
        row.conflict_type,
        f"{row.question[:MAX_TEXT]} {row.rationale[:MAX_TEXT]}",
        generated_at=_timestamp(row.analysis_run.completed_at),
        horizon_months=row.horizon_months,
        probability_low=row.probability_low,
        probability_high=row.probability_high,
        geography=_run_geography(row.analysis_run),
        sources=("GEOINTEL",),
        provenance=Provenance(
            stored_record_id=str(row.id),
            parent_record_id=str(row.analysis_run_id),
            record_metadata={
                "pipeline_version": row.analysis_run.pipeline_version,
                "version": row.version,
            },
        ),
        limitations=("Generated forecast.", *_list(row.unknowns, limit=500)),
    )


def _run_location(relation):
    return (
        joinedload(relation)
        .load_only(AnalysisRun.completed_at, AnalysisRun.pipeline_version)
        .joinedload(AnalysisRun.location)
        .load_only(Location.name, Location.iso_code)
    )


# All statements are fixed ORM queries with bound limits. Search text never reaches SQL.
_READERS: dict[RecordType, tuple[Select, Callable[..., SearchResult]]] = {
    RecordType.CONCEPT: (select(StrategicConcept), _concept),
    RecordType.CASE: (select(HistoricalCase), _case),
    RecordType.CLAIM: (claims_with_work(), _claim),
    RecordType.ANALYSIS: (
        select(StrategicAnalysis).options(_run_location(StrategicAnalysis.analysis_run)),
        _analysis,
    ),
    RecordType.WORK: (select(KnowledgeWork), _work),
    RecordType.SECTION: (
        select(KnowledgeSection).options(joinedload(KnowledgeSection.work)),
        _section,
    ),
    RecordType.EVIDENCE: (
        select(Evidence, Source.name).outerjoin(Source, Evidence.source_id == Source.id),
        _evidence,
    ),
    RecordType.EVENT: (
        select(Event, Source.name).outerjoin(Source, Event.source_id == Source.id),
        _event,
    ),
    RecordType.SIGNAL: (select(ForecastSignal), _signal),
    RecordType.FORECAST: (
        select(Forecast).options(_run_location(Forecast.analysis_run)),
        _forecast,
    ),
}


def _availability_date(result: SearchResult) -> datetime:
    return max(
        value
        for value in (
            result.ingested_at,
            result.parent_ingested_at,
            result.published_at,
            result.retrieved_at,
            result.updated_at,
            result.issued_at,
            result.generated_at,
            result.observed_from,
            result.observed_to,
        )
        if value is not None
    )


def _historical(result: SearchResult, cutoff: date) -> str:
    if _availability_date(result).date() > cutoff:
        return "future"
    year = result.publication_year
    if year and year > cutoff.year:
        return "future"
    if year == cutoff.year and cutoff < date(year, 12, 31):
        return "unknown"
    required = {
        RecordType.CASE: result.observed_to,
        RecordType.EVENT: result.observed_from and result.retrieved_at,
        RecordType.SIGNAL: result.issued_at and result.retrieved_at,
        RecordType.FORECAST: result.generated_at,
        RecordType.ANALYSIS: result.generated_at,
    }
    if result.record_type in required and required[result.record_type] is None:
        return "unknown"
    return "established"


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _overlaps(result: SearchResult, start: date, end: date) -> bool:
    # Use occurrence for observations, issue for forecasts, and generation for local outputs.
    point = result.issued_at or result.generated_at
    if point:
        return start <= point.date() <= end
    if result.observed_from or result.observed_to:
        first = result.observed_from or result.observed_to
        last = result.observed_to or first
        return first.date() <= end and last.date() >= start
    if result.published_at:
        return start <= result.published_at.date() <= end
    if result.publication_year:
        return start.year <= result.publication_year <= end.year
    return False


class _Match:
    def __init__(self, query: SearchQuery):
        self.terms = tuple(dict.fromkeys(_TOKEN.findall(query.text.casefold())))
        self.phrases = [
            " ".join(_TOKEN.findall(part.casefold()))
            for part in re.findall(r'"([^"]+)"', query.text)
        ]
        self.full_phrase = " ".join(_TOKEN.findall(query.text.casefold()))
        self.filters = {
            name: {_normalized(value) for value in getattr(query, name)}
            for name in ("geography", "actors", "sources")
            if getattr(query, name)
        }
        self.dates = (
            (query.date_from or date.min, query.date_to or date.max)
            if query.date_from or query.date_to
            else None
        )

    def rank(self, result: SearchResult) -> SearchResult | None:
        for name, wanted in self.filters.items():
            if wanted.isdisjoint(_normalized(value) for value in getattr(result, name)):
                return None
        if self.dates and not _overlaps(result, *self.dates):
            return None

        reasons = []
        score = 0
        if self.terms:
            fields = (result.title, result.excerpt, *result.geography, *result.actors)
            tokens_by_field = [_TOKEN.findall(value.casefold()) for value in fields]
            phrases_by_field = [f" {' '.join(tokens)} " for tokens in tokens_by_field]
            if any(
                phrase and not any(f" {phrase} " in field for field in phrases_by_field)
                for phrase in self.phrases
            ):
                return None
            words = {token for tokens in tokens_by_field for token in tokens}
            title_words = set(tokens_by_field[0])
            for term in self.terms:
                if term in title_words:
                    score += 4
                    reasons.append(f"title term: {term}")
                elif term in words:
                    score += 2
                    reasons.append(f"exact term: {term}")
                elif any(term in word for word in words):
                    score += 1
                    reasons.append(f"partial term: {term}")
                else:
                    return None
            if len(self.terms) > 1 and any(
                f" {self.full_phrase} " in field for field in phrases_by_field
            ):
                score += 5
                reasons.append("exact query phrase")
        else:
            reasons.append("filter-only match")

        provenance = result.provenance
        absent = {
            "source": not result.sources,
            "provenance": not (
                provenance.source_metadata
                or provenance.record_metadata
                or provenance.url
                or provenance.source_record_id
            ),
            "geography": not result.geography,
            "actors": not result.actors,
            "publication_or_observation_date": not (
                result.published_at
                or result.publication_year
                or result.observed_from
                or result.observed_to
                or result.issued_at
                or result.generated_at
            ),
        }
        return result.model_copy(
            update={
                "relevance_score": score,
                "ranking_reasons": tuple(reasons),
                "missing_metadata": tuple(name for name, missing in absent.items() if missing),
            }
        )


class IntelligenceSearch:
    """Read-only search using a caller-owned session of persisted GEOINTEL records."""

    def __init__(self, session: Session):
        self.session = session

    def search(self, query: SearchQuery) -> SearchPage:
        if self.session.new or self.session.dirty or self.session.deleted:
            raise ValueError("search requires a session without pending writes")
        match = _Match(query)
        statuses = []
        ranked = []
        for kind in RecordType:
            if query.record_types and kind not in query.record_types:
                continue
            records, status = self._read(kind)
            statuses.append(SourceStatus(record_type=kind, status=status))
            unique: dict[str, SearchResult] = {}
            for result in records:
                if query.cutoff:
                    availability = _historical(result, query.cutoff)
                    if availability == "future" or (
                        availability == "unknown" and query.strict_historical
                    ):
                        continue
                    result = result.model_copy(update={"historical_availability": availability})
                existing = unique.get(result.record_id)
                if existing is None or self._version_key(result) > self._version_key(existing):
                    unique[result.record_id] = result
            ranked.extend(hit for item in unique.values() if (hit := match.rank(item)) is not None)

        ranked.sort(key=lambda hit: (-hit.relevance_score, hit.record_type, hit.record_id))
        end = query.offset + query.limit
        return SearchPage(
            results=ranked[query.offset : end],
            sources=statuses,
            total_matches=len(ranked),
            offset=query.offset,
            next_offset=end if end < len(ranked) else None,
            complete=all(source.status == "available" for source in statuses),
        )

    @staticmethod
    def _version_key(result: SearchResult):
        return (
            result.historical_availability != "unknown",
            _availability_date(result),
            result.provenance.stored_record_id,
        )

    def _read(self, kind: RecordType) -> tuple[list[SearchResult], str]:
        statement, adapt = _READERS[kind]
        try:
            # A missing table can abort a PostgreSQL transaction. Isolate each read without
            # flushing pending writes or rolling back the caller's transaction.
            with self.session.no_autoflush, self.session.connection().begin_nested():
                rows = self.session.execute(
                    statement.limit(MAX_ROWS_PER_TYPE + 1).execution_options(populate_existing=True)
                ).all()
                if len(rows) > MAX_ROWS_PER_TYPE:
                    return [], "scan_limit_exceeded"
                return [adapt(*row) for row in rows], "available"
        except SQLAlchemyError:
            return [], "unavailable"
