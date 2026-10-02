"""Bounded GDELT DOC 2.0 ArticleList news discovery connector."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from geointel.domain.schemas import NormalizedNewsReport
from geointel.news.identity import canonicalize_article_url
from geointel.providers.runtime import (
    CollectionAudit,
    CollectionStatus,
    FailureCategory,
    HardenedTransport,
    IntegrationMode,
    TransportError,
    sanitize_mapping,
    sanitize_url,
)

SAFE_LOCATION = re.compile(r"[^\w .,'()\-]", re.UNICODE)


class GDELTError(RuntimeError):
    pass


class GDELTArticle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str = Field(min_length=8, max_length=4000)
    title: str = Field(min_length=1, max_length=2000)
    seendate: datetime | None = None
    domain: str | None = Field(default=None, max_length=500)
    language: str | None = Field(default=None, max_length=100)
    sourcecountry: str | None = Field(default=None, max_length=120)

    @field_validator("seendate", mode="before")
    @classmethod
    def parse_seen_date(cls, value):
        if not value:
            return None
        if isinstance(value, str):
            for pattern in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
                try:
                    return datetime.strptime(value, pattern).replace(tzinfo=UTC)
                except ValueError:
                    pass
        return value


def build_location_query(location: str) -> str:
    # Location is a bounded domain value, never the analysis prompt. Drop URL-like suffixes
    # rather than risking query-string credentials becoming provider parameters or provenance.
    value = location.split("?", 1)[0].split("#", 1)[0]
    cleaned = " ".join(SAFE_LOCATION.sub("", value).split())[:120]
    if len(cleaned) < 2:
        raise ValueError("location cannot form a safe GDELT query")
    return f'"{cleaned}"'


class GDELTConnector:
    connector_name = "GDELT"

    def __init__(
        self,
        base_url: str,
        timeout: float = 10,
        retries: int = 2,
        *,
        transport: HardenedTransport | None = None,
        max_records: int = 250,
        now=None,
    ):
        if not 1 <= max_records <= 250:
            raise ValueError("GDELT ArticleList max_records must be between 1 and 250")
        self.base_url = base_url
        self.max_records = max_records
        self.transport = transport or HardenedTransport(timeout=timeout, retries=retries)
        self._now = now or (lambda: datetime.now(UTC))
        self.last_audit: CollectionAudit | None = None

    def collect(self, location: str, horizon_months: int = 12) -> list[NormalizedNewsReport]:
        del horizon_months  # News collection has its own documented current window.
        audit = CollectionAudit(
            "GDELT", "0.1.3.1", IntegrationMode.OFFICIAL_API, "gdelt-doc2-artlist-json-v1"
        )
        self.last_audit = audit
        end = self._now().astimezone(UTC).replace(microsecond=0)
        start = end - timedelta(days=90)
        query = build_location_query(location)
        audit.provider_restrictions = {
            "effective_query": query,
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "window_days": 90,
            "max_records": self.max_records,
            "articlelist_has_no_pagination": True,
            "collection_mode": "fresh_network_fetch",
            "continuous_historical_availability_not_asserted": True,
            "discovery_sensor_not_event_source": True,
        }
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": self.max_records,
            "startdatetime": start.strftime("%Y%m%d%H%M%S"),
            "enddatetime": end.strftime("%Y%m%d%H%M%S"),
        }
        try:
            payload, request_url, attempts = self.transport.get_json(
                self.base_url, params=params, retry_rate_limited=False
            )
            audit.request_count = attempts
            audit.page_count = 1
            rows = self._articles(payload)
            audit.received = len(rows)
            output: list[NormalizedNewsReport] = []
            seen: set[str] = set()
            retrieved = self._now().astimezone(UTC)
            for raw in rows:
                try:
                    item = self.normalize(raw, location, retrieved, request_url, start, end, query)
                    if item.canonical_url in seen:
                        audit.duplicates += 1
                        continue
                    seen.add(item.canonical_url)
                    output.append(item)
                    audit.accepted += 1
                except (ValidationError, ValueError, TypeError) as exc:
                    audit.reject(exc)
            audit.truncated = len(rows) >= self.max_records
            audit.finish(
                CollectionStatus.PARTIAL
                if audit.rejected or audit.truncated
                else CollectionStatus.SUCCEEDED
            )
            return output
        except TransportError as exc:
            audit.failure_category = exc.category
            audit.rate_limited = exc.category == FailureCategory.RATE_LIMITED
            audit.retry_after_seconds = exc.retry_after_seconds
            audit.request_count = exc.request_count or audit.request_count
            audit.failure_reason = str(exc)
            audit.finish(CollectionStatus.FAILED)
            error = GDELTError(str(exc))
            error.category = exc.category
            raise error from exc
        except GDELTError as exc:
            audit.failure_category = FailureCategory.SCHEMA_MISMATCH
            audit.failure_reason = str(exc)
            audit.finish(CollectionStatus.FAILED)
            exc.category = FailureCategory.SCHEMA_MISMATCH
            raise

    @staticmethod
    def _articles(payload: Any) -> list[Any]:
        if not isinstance(payload, dict) or not isinstance(payload.get("articles"), list):
            raise GDELTError("GDELT ArticleList response schema mismatch")
        return payload["articles"]

    @staticmethod
    def normalize(raw, location, retrieved, request_url, start, end, query):
        record = GDELTArticle.model_validate(raw)
        canonical = canonicalize_article_url(record.url)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        publication = record.seendate
        temporal_alignment = "unknown"
        if publication:
            temporal_alignment = (
                "within_requested_window"
                if start <= publication <= end
                else "outside_requested_window"
            )
        return NormalizedNewsReport(
            source_record_id=digest,
            canonical_url=canonical,
            title=record.title,
            publisher=record.domain,
            publication_timestamp=publication,
            retrieval_timestamp=retrieved,
            language=record.language,
            source_country=record.sourcecountry,
            requested_geography=location,
            provider_geography=None,
            geographic_alignment_status="unknown",
            geographic_alignment_notes=[
                "Query relevance does not establish geographic alignment; ArticleList provides "
                "no article event geography used by this schema."
            ],
            temporal_classification="publication_timestamp_not_event_date",
            temporal_alignment=temporal_alignment,
            identity_metadata={
                "method": "conservative_canonical_url_sha256",
                "canonical_url_sha256": digest,
                "title_similarity_used": False,
            },
            syndication_metadata={
                "cluster_id": None,
                "independence_status": "unknown",
                "independent_corroboration": False,
            },
            provenance={
                "discovery_provider": "GDELT",
                "underlying_publisher": record.domain,
                "endpoint": "DOC 2.0",
                "mode": "ArticleList",
                "format": "json",
                "effective_query": query,
                "requested_window": {"start": start.isoformat(), "end": end.isoformat()},
                "retrieval_url": sanitize_url(request_url),
                "provider_fields": sanitize_mapping(
                    {
                        key: raw[key]
                        for key in (
                            "url",
                            "title",
                            "seendate",
                            "domain",
                            "language",
                            "sourcecountry",
                        )
                        if key in raw
                    }
                ),
                "untrusted_media_content": True,
                "article_not_fetched": True,
                "not_event_or_evidence": True,
                "collection_mode": "fresh_network_fetch",
                "continuous_historical_availability_not_asserted": True,
                "publication_timestamp_not_event_occurrence": True,
            },
        )
