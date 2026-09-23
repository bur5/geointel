import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

from geointel.domain.schemas import NormalizedOperationalEvent
from geointel.providers.acled_auth import ACLEDOAuthClient
from geointel.providers.runtime import (
    CollectionAudit,
    CollectionStatus,
    FailureCategory,
    HardenedTransport,
    IntegrationMode,
    paginate,
    sanitize_mapping,
    sanitize_url,
)


class ACLEDError(RuntimeError):
    pass


class ACLEDRawEvent(BaseModel):
    event_id: str | int = Field(validation_alias=AliasChoices("event_id_cnty", "event_id"))
    event_date: datetime
    event_type: str = Field(max_length=100)
    sub_event_type: str | None = Field(default=None, max_length=120)
    country: str = Field(max_length=120)
    admin1: str | None = Field(default=None, max_length=160)
    admin2: str | None = Field(default=None, max_length=160)
    admin3: str | None = Field(default=None, max_length=160)
    location: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    actor1: str | None = Field(default=None, max_length=300)
    actor2: str | None = Field(default=None, max_length=300)
    assoc_actor_1: str | None = Field(default=None, max_length=300)
    assoc_actor_2: str | None = Field(default=None, max_length=300)
    fatalities: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=10_000)
    source: str | None = Field(default=None, max_length=1000)
    source_scale: str | None = Field(default=None, max_length=120)
    disorder_type: str | None = Field(default=None, max_length=120)
    timestamp: datetime | None = None

    @field_validator("event_date", mode="before")
    @classmethod
    def parse_official_date(cls, value):
        if isinstance(value, str):
            for pattern in ("%d %B %Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value, pattern).replace(tzinfo=UTC)
                except ValueError:
                    pass
        return value


class ACLEDConnector:
    """Fetch observed event reports from an operator-verified ACLED adapter."""

    connector_name = "ACLED"

    def __init__(
        self,
        base_url: str,
        endpoint_path: str | None,
        timeout: float = 10,
        retries: int = 2,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        *,
        official_api: bool = False,
        oauth: ACLEDOAuthClient | None = None,
        transport: HardenedTransport | None = None,
        max_pages: int = 10,
        max_records: int = 10_000,
    ):
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if retries < 0:
            raise ValueError("retries must not be negative")
        if endpoint_path and not base_url.strip():
            raise ValueError("base_url is required when endpoint_path is configured")
        self.base_url, self.endpoint_path = base_url.rstrip("/"), endpoint_path
        self.timeout, self.retries, self._client, self._sleep = timeout, retries, client, sleep
        self.official_api, self.oauth = official_api, oauth
        self.transport = transport or HardenedTransport(
            timeout=timeout, retries=retries, client=client, sleep=sleep
        )
        self.max_pages, self.max_records = max_pages, max_records
        self.last_audit: CollectionAudit | None = None

    def collect(self, location: str, horizon_months: int = 12) -> list[NormalizedOperationalEvent]:
        if self.official_api:
            return self._collect_official(location)
        if not self.endpoint_path:
            raise ACLEDError("ACLED verified adapter endpoint is not configured")
        if self._client is not None:
            return self._collect(self._client, location)
        with httpx.Client(timeout=self.timeout) as client:
            return self._collect(client, location)

    def _collect_official(self, location: str) -> list[NormalizedOperationalEvent]:
        if not self.oauth:
            raise ACLEDError("ACLED OAuth client is not configured")
        audit = CollectionAudit(
            "ACLED", "0.1.2", IntegrationMode.OFFICIAL_API, "acled-events-official-v1"
        )
        self.last_audit = audit
        retrieval_urls: dict[str, str] = {}
        # The operational ACLED layer is explicitly a rolling 0-90 day window. Filter
        # at the provider boundary so historical rows are not downloaded and then
        # misrepresented as operational input. ACLED documents event_date BETWEEN.
        window_end = datetime.now(UTC).date()
        window_start = window_end - timedelta(days=90)
        event_date_range = f"{window_start.isoformat()}|{window_end.isoformat()}"

        def fetch(cursor):
            token = self.oauth.access_token()
            payload, request_url, _ = self.transport.get_json(
                f"{self.base_url}/acled/read",
                params={
                    "country": location,
                    "event_date": event_date_range,
                    "event_date_where": "BETWEEN",
                    "cursor": "0" if cursor is None else cursor,
                    "limit": min(self.max_records, 5000),
                },
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ValueError("ACLED response schema mismatch")
            rows = payload["data"]
            restrictions = payload.get("data_query_restrictions")
            if restrictions is not None:
                if not isinstance(restrictions, dict):
                    raise ValueError("ACLED data_query_restrictions is malformed")
                audit.provider_restrictions = sanitize_mapping(restrictions)
            if not all(isinstance(row, dict) for row in rows):
                raise ValueError("ACLED data contains a non-object")
            next_cursor = payload.get("next_cursor")
            if next_cursor is not None and not isinstance(next_cursor, (str, int)):
                raise ValueError("ACLED next_cursor is malformed")
            for row in rows:
                if "event_id_cnty" in row:
                    retrieval_urls[str(row["event_id_cnty"])] = request_url
            return rows, None if next_cursor is None else str(next_cursor)

        rows = paginate(
            fetch,
            identity=lambda row: str(row["event_id_cnty"]),
            audit=audit,
            max_pages=self.max_pages,
            max_records=self.max_records,
        )
        if not rows and self._recency_restricted(audit.provider_restrictions):
            audit.failure_category = FailureCategory.RECENCY_RESTRICTED
            audit.failure_reason = (
                "ACLED provider access restricts data recency for the requested operational window; "
                "an empty result must not be interpreted as absence of events"
            )
            audit.finish(CollectionStatus.PARTIAL)

        normalized = []
        for row in rows:
            try:
                normalized.append(
                    self.normalize(row, location, retrieval_urls.get(str(row.get("event_id_cnty"))))
                )
            except (ValidationError, ValueError, TypeError) as exc:
                audit.reject(exc)
        if audit.rejected and audit.status == CollectionStatus.SUCCEEDED:
            audit.finish(CollectionStatus.PARTIAL)
        if not rows and audit.failure_category:
            error = ACLEDError(f"ACLED collection failed: {audit.failure_reason}")
            error.category = audit.failure_category
            raise error
        return normalized

    def _collect(self, client: httpx.Client, location: str) -> list[NormalizedOperationalEvent]:
        url = f"{self.base_url}/{self.endpoint_path.lstrip('/')}"
        last: Exception | None = None
        attempts = 0
        for attempt in range(self.retries + 1):
            attempts = attempt + 1
            try:
                response = client.get(url, params={"location": location}, timeout=self.timeout)
                if self._transient(response.status_code):
                    raise httpx.HTTPStatusError(
                        "transient ACLED response", request=response.request, response=response
                    )
                response.raise_for_status()
                if len(response.content) > 5_000_000:
                    raise ValueError("ACLED adapter response exceeds 5 MB")
                records = self._records(response.json())
                deduplicated: dict[str, NormalizedOperationalEvent] = {}
                for raw in records:
                    item = self.normalize(raw, location, str(response.request.url))
                    deduplicated.setdefault(item.source_record_id, item)
                return list(deduplicated.values())
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last = exc
                if isinstance(exc, httpx.HTTPStatusError) and not self._transient(
                    exc.response.status_code
                ):
                    break
                if attempt < self.retries:
                    self._sleep(0.05 * (2**attempt))
            except (ValueError, ValidationError, TypeError) as exc:
                last = exc
                break
        raise ACLEDError(f"ACLED retrieval failed after {attempts} attempts: {last}") from last

    @staticmethod
    def _recency_restricted(restrictions: dict[str, Any]) -> bool:
        if not restrictions:
            return False
        value = restrictions.get("data_recency")
        if value in (None, False, "", [], {}):
            return False
        if isinstance(value, str) and value.strip().casefold() in {
            "none", "unrestricted", "real-time", "realtime", "current"
        }:
            return False
        return True

    @staticmethod
    def _transient(status: int) -> bool:
        return status in {408, 429} or status >= 500

    @staticmethod
    def _records(payload: Any) -> list[dict]:
        if not isinstance(payload, dict) or set(payload) != {"events"}:
            raise ValueError("ACLED adapter response must contain only an events list")
        records = payload["events"]
        if not isinstance(records, list) or not all(isinstance(x, dict) for x in records):
            raise ValueError("ACLED adapter events must be a list of objects")
        if len(records) > 10_000:
            raise ValueError("ACLED adapter response exceeds 10000 records")
        return records

    def normalize(
        self, raw: dict, requested_location: str, retrieval_url: str | None = None
    ) -> NormalizedOperationalEvent:
        record = ACLEDRawEvent.model_validate(raw)
        record_id = str(record.event_id)
        if len(record_id) > 200:
            raise ValueError("ACLED event id exceeds 200 characters")
        notes = []
        if record.country.casefold() != requested_location.casefold():
            notes.append(
                f"geographic mismatch: requested {requested_location}, received {record.country}"
            )
        actors = [x for x in (record.actor1, record.actor2) if x]
        associated = [x for x in (record.assoc_actor_1, record.assoc_actor_2) if x]
        retrieved_at = datetime.now(UTC)
        event_date = record.event_date
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=UTC)
        age = retrieved_at - event_date
        temporal = "current_window" if timedelta(0) <= age <= timedelta(days=90) else "historical"
        if age > timedelta(days=90):
            notes.append("stale event: event date is outside the documented 0-90 day window")
        elif age < timedelta(0):
            notes.append("temporal mismatch: event date is later than retrieval time")
        return NormalizedOperationalEvent(
            source_record_id=record_id,
            event_date=record.event_date,
            event_type=record.event_type,
            sub_event_type=record.sub_event_type,
            country=record.country,
            admin1=record.admin1,
            admin2=record.admin2,
            admin3=record.admin3,
            locality=record.location,
            latitude=record.latitude,
            longitude=record.longitude,
            actors=actors,
            associated_actors=associated,
            fatalities=record.fatalities,
            notes=record.notes,
            source_description=record.source,
            source_scale=record.source_scale,
            disorder_type=record.disorder_type,
            updated_at=record.timestamp,
            retrieved_at=retrieved_at,
            source_url=sanitize_url(retrieval_url) if retrieval_url else None,
            alignment_status="mismatch" if notes else "aligned",
            alignment_notes=notes,
            temporal_classification=temporal,
            provenance={
                "provider": "ACLED",
                "record_id": record_id,
                "retrieval_url": sanitize_url(retrieval_url) if retrieval_url else None,
                "schema": (
                    "geointel-acled-official-v1"
                    if self.official_api
                    else "geointel-acled-adapter-v1"
                ),
                "endpoint": "acled/read" if self.official_api else "operator-adapter",
                "observed_report_not_prediction": True,
                "fatalities_are_reported_not_precise": True,
                "operational_window_days": 90,
                "raw_adapter_record": sanitize_mapping(record.model_dump(mode="json")),
            },
        )

    model_config = ConfigDict(extra="forbid")
