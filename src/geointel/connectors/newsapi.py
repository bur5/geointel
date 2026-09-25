"""Bounded NewsAPI /v2/everything discovery connector (Developer plan by default)."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from geointel.domain.schemas import NormalizedNewsReport
from geointel.news.identity import canonicalize_article_url
from geointel.news.query import NewsQueryPlan, plan_news_queries
from geointel.providers.runtime import (
    CollectionAudit,
    CollectionStatus,
    FailureCategory,
    HardenedTransport,
    IntegrationMode,
    TransportError,
    sanitize_url,
)

SAFE_QUERY = re.compile(r"[^\w .,'()\-]", re.UNICODE)


class NewsAPIError(RuntimeError):
    pass


class NewsAPISource(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | None = Field(default=None, max_length=500)
    name: str | None = Field(default=None, max_length=500)


class NewsAPIArticle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source: NewsAPISource = Field(default_factory=NewsAPISource)
    author: str | None = Field(default=None, max_length=1000)
    title: str = Field(min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=5000)
    url: str = Field(min_length=8, max_length=4000)
    publishedAt: datetime


ERROR_MAP = {
    "apiKeyDisabled": FailureCategory.AUTHENTICATION_ERROR,
    "apiKeyInvalid": FailureCategory.AUTHENTICATION_ERROR,
    "apiKeyMissing": FailureCategory.AUTHENTICATION_ERROR,
    "apiKeyExhausted": FailureCategory.QUOTA_EXHAUSTED,
    "rateLimited": FailureCategory.RATE_LIMITED,
    "parameterInvalid": FailureCategory.INVALID_REQUEST,
    "parametersMissing": FailureCategory.INVALID_REQUEST,
    "sourcesTooMany": FailureCategory.INVALID_REQUEST,
    "sourceDoesNotExist": FailureCategory.INVALID_REQUEST,
    "unexpectedError": FailureCategory.PROVIDER_5XX,
}


class NewsAPIConnector:
    connector_name = "NEWSAPI"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 10,
        retries: int = 0,
        *,
        transport: HardenedTransport | None = None,
        max_pages: int = 2,
        max_records: int = 100,
        request_budget: int = 2,
        page_size: int = 50,
        window_days: int = 7,
        entitlement: str = "developer",
        now=None,
    ):
        if not api_key:
            raise ValueError("NEWSAPI_API_KEY is required")
        if not 1 <= max_pages <= 10 or not 1 <= request_budget <= 10:
            raise ValueError("NewsAPI request bounds must be between 1 and 10")
        if not 1 <= max_records <= 1000 or not 1 <= page_size <= 100:
            raise ValueError("NewsAPI record/page bounds are invalid")
        if not 2 <= window_days <= 30:
            raise ValueError("NewsAPI discovery window must be between 2 and 30 days")
        self.url = base_url.rstrip("/") + "/v2/everything"
        self.api_key, self.max_pages, self.max_records = api_key, max_pages, max_records
        self.request_budget, self.page_size, self.window_days = (
            request_budget,
            page_size,
            window_days,
        )
        self.entitlement = entitlement.casefold()
        self.transport = transport or HardenedTransport(timeout=timeout, retries=retries)
        self._now = now or (lambda: datetime.now(UTC))
        self.last_audit: CollectionAudit | None = None
        self.last_query_plan: NewsQueryPlan | None = None
        self.last_query_accepted_counts: dict[str, int] = {}

    def collect(self, location: str, horizon_months: int = 12) -> list[NormalizedNewsReport]:
        del horizon_months
        audit = CollectionAudit(
            "NEWSAPI", "0.1.4", IntegrationMode.OFFICIAL_API, "newsapi-everything-v1"
        )
        self.last_audit = audit
        end = self._now().astimezone(UTC).replace(microsecond=0) - timedelta(hours=24)
        start = end - timedelta(days=self.window_days)
        try:
            plan = plan_news_queries(location, request_budget=self.request_budget)
        except ValueError as exc:
            raise NewsAPIError(str(exc)) from exc
        self.last_query_plan = plan
        self.last_query_accepted_counts = {}
        audit.provider_restrictions = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "window_days": self.window_days,
            "developer_plan": self.entitlement == "developer",
            "development_testing_only": self.entitlement == "developer",
            "daily_request_limit": 100 if self.entitlement == "developer" else None,
            "article_delay_hours": 24 if self.entitlement == "developer" else None,
            "searchable_history_approximately_days": 30
            if self.entitlement == "developer"
            else None,
            "max_pages": self.max_pages,
            "max_records": self.max_records,
            "request_budget": self.request_budget,
            "not_realtime_event_coverage": True,
        }
        output, seen, total = [], set(), None
        try:
            # The global request budget is allocated across query families. It is never
            # multiplied by either query count or max_pages.
            for query in plan.queries[: min(self.max_pages, self.request_budget)]:
                payload, request_url, attempts = self.transport.get_json(
                    self.url,
                    params={
                        "q": query.query_text,
                        "from": start.isoformat(),
                        "to": end.isoformat(),
                        "language": "en",
                        "sortBy": "publishedAt",
                        "pageSize": self.page_size,
                        "page": 1,
                    },
                    headers={"X-Api-Key": self.api_key},
                    retry_rate_limited=False,
                )
                audit.request_count += attempts
                audit.page_count += 1
                rows, total = self._articles(payload)
                audit.received += len(rows)
                retrieved = self._now().astimezone(UTC)
                accepted_before = audit.accepted
                for raw in rows:
                    if len(output) >= self.max_records:
                        audit.truncated = True
                        break
                    try:
                        item = self.normalize(raw, location, retrieved, request_url, start, end)
                        if item.canonical_url in seen:
                            audit.duplicates += 1
                        else:
                            seen.add(item.canonical_url)
                            output.append(item)
                            audit.accepted += 1
                    except (ValidationError, ValueError, TypeError) as exc:
                        audit.reject(exc)
                self.last_query_accepted_counts[query.signal_family] = (
                    audit.accepted - accepted_before
                )
                if audit.truncated:
                    break
            audit.truncated |= bool(total is not None and audit.received < total)
            audit.finish(
                CollectionStatus.PARTIAL
                if audit.rejected or audit.truncated
                else CollectionStatus.SUCCEEDED
            )
            return output
        except TransportError as exc:
            category = ERROR_MAP.get(getattr(exc, "provider_code", None), exc.category)
            audit.failure_category = category
            audit.rate_limited = category == FailureCategory.RATE_LIMITED
            audit.request_count += exc.request_count or 1
            audit.failure_reason = f"NewsAPI request failed: {category.value}"
            audit.finish(CollectionStatus.FAILED)
            error = NewsAPIError(audit.failure_reason)
            error.category = category
            raise error from exc
        except NewsAPIError as exc:
            audit.failure_category = FailureCategory.SCHEMA_MISMATCH
            audit.failure_reason = str(exc)
            audit.finish(CollectionStatus.FAILED)
            exc.category = FailureCategory.SCHEMA_MISMATCH
            raise

    @staticmethod
    def _articles(payload: Any) -> tuple[list[Any], int]:
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise NewsAPIError("NewsAPI response schema mismatch")
        if not isinstance(payload.get("articles"), list) or not isinstance(
            payload.get("totalResults"), int
        ):
            raise NewsAPIError("NewsAPI response schema mismatch")
        return payload["articles"], max(0, payload["totalResults"])

    @staticmethod
    def normalize(raw, location, retrieved, request_url, start, end):
        record = NewsAPIArticle.model_validate(raw)
        published = record.publishedAt.astimezone(UTC)
        canonical = canonicalize_article_url(record.url)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return NormalizedNewsReport(
            provider="NEWSAPI",
            source_record_id=digest,
            canonical_url=canonical,
            title=record.title,
            publisher=record.source.name,
            publication_timestamp=published,
            retrieval_timestamp=retrieved,
            requested_geography=location,
            geographic_alignment_notes=["Query relevance does not establish event geography."],
            temporal_classification="publication_timestamp_not_event_date",
            temporal_alignment="within_requested_window"
            if start <= published <= end
            else "outside_requested_window",
            identity_metadata={
                "method": "conservative_canonical_url_sha256",
                "canonical_url_sha256": digest,
                "title_similarity_used": False,
            },
            syndication_metadata={
                "independence_status": "UNKNOWN",
                "named_upstream": None,
                "independent_corroboration": False,
            },
            provenance={
                "discovery_provider": "NEWSAPI",
                "source_id": record.source.id,
                "underlying_publisher": record.source.name,
                "author": record.author,
                "description": record.description,
                "endpoint": "/v2/everything",
                "retrieval_url": sanitize_url(request_url),
                "requested_window": {"start": start.isoformat(), "end": end.isoformat()},
                "publishedAt_semantics": "publication_timestamp_not_event_occurrence",
                "untrusted_media_content": True,
                "article_not_fetched": True,
                "not_event_or_evidence": True,
            },
        )
