from datetime import UTC, date, datetime
from typing import Any

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from geointel.domain.schemas import Confidence, NormalizedEvidence
from geointel.geography import CountryIdentity, resolve_country
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


class UCDPError(RuntimeError):
    def __init__(self, message: str, category: FailureCategory = FailureCategory.UNKNOWN):
        self.category = category
        super().__init__(message)


class UCDPRawRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int | str
    country: str
    country_id: int | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    coverage_end: date | None = None
    reference_date: date | None = None
    type_of_violence: int | None = None
    best: int | None = Field(
        default=None, ge=0, validation_alias=AliasChoices("best", "deaths_best")
    )
    low: int | None = Field(default=None, ge=0, validation_alias=AliasChoices("low", "deaths_low"))
    high: int | None = Field(
        default=None, ge=0, validation_alias=AliasChoices("high", "deaths_high")
    )
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    source_article: str | None = None


class UCDPConnector:
    """UCDP GED connector; official mode implements the documented versioned API."""

    connector_name = "UCDP"

    def __init__(
        self,
        base_url: str,
        api_version: str,
        endpoint_path: str | None = None,
        access_token: str | None = None,
        timeout: float = 10,
        retries: int = 2,
        client: httpx.Client | None = None,
        sleep=None,
        *,
        official_api: bool = False,
        page_size: int = 100,
        max_pages: int = 10,
        max_records: int = 10_000,
        max_bytes: int = 5_000_000,
        dataset_role: str = "annual_historical",
    ):
        if timeout <= 0 or retries < 0:
            raise ValueError(
                "timeout must be greater than zero"
                if timeout <= 0
                else "retries must not be negative"
            )
        if not 1 <= page_size <= 1000 or not 1 <= max_pages <= 100 or max_records < 1:
            raise ValueError("UCDP collection bounds are invalid")
        self.base_url, self.api_version = base_url.rstrip("/"), api_version
        self.endpoint_path, self.access_token, self.official_api = (
            endpoint_path,
            access_token,
            official_api,
        )
        self.page_size, self.max_pages, self.max_records = page_size, max_pages, max_records
        if dataset_role not in {"annual_historical", "candidate_recent"}:
            raise ValueError("UCDP dataset_role must be annual_historical or candidate_recent")
        self.dataset_role = dataset_role
        self.transport = HardenedTransport(
            timeout=timeout,
            retries=retries,
            max_bytes=max_bytes,
            client=client,
            sleep=sleep or __import__("time").sleep,
        )
        self.last_audit: CollectionAudit | None = None

    def collect(self, location: str, horizon_months: int = 12) -> list[NormalizedEvidence]:
        if self.official_api:
            return self._collect_official(location)
        if not self.endpoint_path:
            raise UCDPError(
                "UCDP endpoint path is not configured; consult current UCDP API documentation"
            )
        return self._collect_adapter(location)

    def _collect_adapter(self, location: str) -> list[NormalizedEvidence]:
        url = f"{self.base_url}/{self.endpoint_path.lstrip('/')}"
        headers = {"x-ucdp-access-token": self.access_token} if self.access_token else None
        try:
            payload, retrieval_url, _ = self.transport.get_json(
                url, params={"country": location, "version": self.api_version}, headers=headers
            )
            return [self.normalize(row, location, retrieval_url) for row in self._records(payload)]
        except (TransportError, ValueError, ValidationError, TypeError) as exc:
            retry_categories = {
                FailureCategory.TIMEOUT,
                FailureCategory.NETWORK_ERROR,
                FailureCategory.RATE_LIMITED,
                FailureCategory.PROVIDER_5XX,
            }
            attempts = (
                self.transport.retries + 1
                if getattr(exc, "category", None) in retry_categories
                else 1
            )
            raise UCDPError(
                f"UCDP retrieval failed after {attempts} attempts: {exc}",
                getattr(exc, "category", FailureCategory.SCHEMA_MISMATCH),
            ) from exc

    def _collect_official(self, location: str) -> list[NormalizedEvidence]:
        if not self.access_token:
            raise UCDPError(
                "UCDP access token is not configured", FailureCategory.CONFIGURATION_ERROR
            )
        if not self.api_version.strip():
            raise UCDPError("UCDP dataset version is required", FailureCategory.CONFIGURATION_ERROR)
        try:
            country = resolve_country(location)
        except ValueError as exc:
            raise UCDPError(str(exc), FailureCategory.CONFIGURATION_ERROR) from exc
        audit = CollectionAudit(
            "UCDP", "0.1.6.1", IntegrationMode.OFFICIAL_API, "ucdp-gedevents-v1"
        )
        self.last_audit = audit
        output: list[NormalizedEvidence] = []
        seen: set[str] = set()
        total_pages: int | None = None
        url = f"{self.base_url}/gedevents/{self.api_version}"
        audit.provider_restrictions = {
            "resource": "gedevents",
            "dataset_version": self.api_version,
            "requested_geography": location,
            "resolved_country_id": country.gw_code,
            "page_size": self.page_size,
            "temporal_role": self.dataset_role,
            "coverage_semantics": self._coverage_semantics(),
            "sanitized_endpoint": sanitize_url(url),
        }
        try:
            for page in range(1, self.max_pages + 1):
                audit.provider_restrictions["page"] = page
                payload, retrieval_url, attempts = self.transport.get_json(
                    url,
                    params={"Country": country.gw_code, "pagesize": self.page_size, "page": page},
                    headers={"x-ucdp-access-token": self.access_token},
                )
                audit.request_count += attempts
                audit.page_count += 1
                records, declared_pages = self._official_envelope(payload)
                if total_pages is None:
                    total_pages = declared_pages
                    if total_pages < 0 or total_pages > 1_000_000:
                        raise UCDPError(
                            "UCDP returned malformed TotalPages", FailureCategory.PAGINATION_ERROR
                        )
                elif declared_pages != total_pages:
                    raise UCDPError(
                        "UCDP TotalPages changed during collection",
                        FailureCategory.PAGINATION_ERROR,
                    )
                audit.received += len(records)
                for raw in records:
                    try:
                        record_id = str(raw["id"])
                        if record_id in seen:
                            audit.duplicates += 1
                            continue
                        item = self.normalize(raw, location, retrieval_url, country)
                        seen.add(record_id)
                        output.append(item)
                        audit.accepted += 1
                    except Exception as exc:
                        audit.reject(exc)
                    if len(output) >= self.max_records:
                        audit.truncated = True
                        audit.finish(CollectionStatus.PARTIAL)
                        return output
                if page >= total_pages:
                    audit.finish(
                        CollectionStatus.PARTIAL if audit.rejected else CollectionStatus.SUCCEEDED
                    )
                    return output
            audit.truncated = total_pages is not None and total_pages > self.max_pages
            audit.finish(
                CollectionStatus.PARTIAL
                if audit.truncated or audit.rejected
                else CollectionStatus.SUCCEEDED
            )
            return output
        except (TransportError, UCDPError) as exc:
            audit.failure_category = getattr(exc, "category", FailureCategory.UNKNOWN)
            audit.rate_limited = audit.failure_category == FailureCategory.RATE_LIMITED
            audit.failure_reason = str(exc)
            audit.finish(CollectionStatus.PARTIAL if output else CollectionStatus.FAILED)
            if output:
                return output
            raise UCDPError(str(exc), audit.failure_category) from exc

    @staticmethod
    def _official_envelope(payload: Any) -> tuple[list[dict[str, Any]], int]:
        if not isinstance(payload, dict) or not isinstance(payload.get("Result"), list):
            raise UCDPError("UCDP response schema mismatch", FailureCategory.SCHEMA_MISMATCH)
        pages = payload.get("TotalPages")
        if isinstance(pages, bool) or not isinstance(pages, int):
            raise UCDPError("UCDP returned malformed TotalPages", FailureCategory.PAGINATION_ERROR)
        if not all(isinstance(row, dict) for row in payload["Result"]):
            raise UCDPError("UCDP Result contains a non-object", FailureCategory.SCHEMA_MISMATCH)
        return payload["Result"], pages

    @staticmethod
    def _records(payload: Any) -> list[dict]:
        if not isinstance(payload, dict):
            raise ValueError("UCDP response must be an object envelope")
        keys = [key for key in ("Result", "results") if key in payload]
        if len(keys) != 1 or not isinstance(payload[keys[0]], list):
            raise ValueError("UCDP response envelope must contain one list named Result or results")
        if not all(isinstance(item, dict) for item in payload[keys[0]]):
            raise ValueError("UCDP response records must be objects")
        return payload[keys[0]]

    def normalize(
        self,
        raw: dict,
        location: str,
        retrieval_url: str | None = None,
        resolved_country: CountryIdentity | None = None,
    ) -> NormalizedEvidence:
        record = UCDPRawRecord.model_validate(raw)
        if resolved_country and record.country_id != resolved_country.gw_code:
            raise ValueError("UCDP record country_id does not match resolved request geography")
        return NormalizedEvidence(
            source_name="UCDP",
            source_record_id=str(record.id),
            title=f"UCDP conflict record {record.id}",
            summary=(
                f"UCDP coded violence record for {record.country}; best deaths: "
                f"{record.best if record.best is not None else 'unknown'}."
            ),
            published_at=None,
            event_date=record.date_start,
            retrieved_at=datetime.now(UTC),
            geographic_scope=location,
            reliability=Confidence.HIGH,
            provenance={
                "provider": "UCDP",
                "dataset": "GED Candidate" if self.dataset_role == "candidate_recent" else "GED",
                "temporal_role": self.dataset_role,
                "coverage_semantics": self._coverage_semantics(),
                "endpoint": "gedevents",
                "dataset_version": self.api_version,
                "record_id": str(record.id),
                "country": record.country,
                "country_id": record.country_id,
                "requested_geography": location,
                "resolved_ucdp_country_id": resolved_country.gw_code if resolved_country else None,
                "date_end": record.date_end.isoformat() if record.date_end else None,
                "coverage_end": record.coverage_end.isoformat() if record.coverage_end else None,
                "reference_date": (
                    record.reference_date.isoformat() if record.reference_date else None
                ),
                "type_of_violence": record.type_of_violence,
                "fatalities": {
                    "best": record.best,
                    "low": record.low,
                    "high": record.high,
                },
                "coordinates": {"latitude": record.latitude, "longitude": record.longitude},
                "source_article": sanitize_mapping(record.source_article),
                "retrieval_url": sanitize_url(retrieval_url) if retrieval_url else None,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "observed_historical_not_forecast": True,
                "not_realtime": True,
            },
        )

    def _coverage_semantics(self) -> str:
        return (
            "recent_candidate_observed_conflict_not_realtime_not_evidence_of_absence"
            if self.dataset_role == "candidate_recent"
            else "annual_historical_base_rate_not_current_operational_coverage"
        )
