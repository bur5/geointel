import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from geointel.domain.schemas import Confidence, NormalizedEvidence


class UCDPError(RuntimeError):
    pass


class UCDPRawRecord(BaseModel):
    id: int | str
    country: str
    date_start: datetime | None = None
    date_end: datetime | None = None
    type_of_violence: int | None = None
    deaths_best: int | None = Field(default=None, ge=0)
    source_article: str | None = None


class UCDPConnector:
    """Adapter for an explicitly configured UCDP-compatible endpoint."""

    def __init__(
        self,
        base_url: str,
        api_version: str,
        endpoint_path: str | None = None,
        access_token: str | None = None,
        timeout: float = 10,
        retries: int = 2,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if retries < 0:
            raise ValueError("retries must not be negative")
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self.endpoint_path = endpoint_path
        self.access_token = access_token
        self.timeout = timeout
        self.retries = retries
        self._client = client
        self._sleep = sleep

    def collect(self, location: str) -> list[NormalizedEvidence]:
        if not self.endpoint_path:
            raise UCDPError(
                "UCDP endpoint path is not configured; consult current UCDP API documentation"
            )
        if self._client is not None:
            return self._collect(self._client, location)
        with httpx.Client(timeout=self.timeout) as client:
            return self._collect(client, location)

    def _collect(self, client: httpx.Client, location: str) -> list[NormalizedEvidence]:
        headers = {"Authorization": f"Bearer {self.access_token}"} if self.access_token else {}
        url = f"{self.base_url}/{self.endpoint_path.lstrip('/')}"
        last: Exception | None = None
        attempts_used = 0
        for attempt in range(self.retries + 1):
            attempts_used = attempt + 1
            try:
                response = client.get(
                    url,
                    params={"country": location, "version": self.api_version},
                    headers=headers,
                    timeout=self.timeout,
                )
                if self._is_transient(response.status_code):
                    raise httpx.HTTPStatusError(
                        "transient UCDP response", request=response.request, response=response
                    )
                response.raise_for_status()
                records = self._records(response.json())
                return [
                    self.normalize(item, location, str(response.request.url)) for item in records
                ]
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last = exc
                if isinstance(exc, httpx.HTTPStatusError) and not self._is_transient(
                    exc.response.status_code
                ):
                    break
                if attempt < self.retries:
                    self._sleep(0.05 * (2**attempt))
            except (ValueError, ValidationError, TypeError) as exc:
                last = exc
                break
        raise UCDPError(f"UCDP retrieval failed after {attempts_used} attempts: {last}") from last

    @staticmethod
    def _is_transient(status_code: int) -> bool:
        return status_code in {408, 429} or status_code >= 500

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
        self, raw: dict, location: str, retrieval_url: str | None = None
    ) -> NormalizedEvidence:
        record = UCDPRawRecord.model_validate(raw)
        return NormalizedEvidence(
            source_name="UCDP",
            source_record_id=str(record.id),
            title=f"UCDP conflict record {record.id}",
            summary=(
                f"UCDP coded violence record for {record.country}; best deaths: "
                f"{record.deaths_best if record.deaths_best is not None else 'unknown'}."
            ),
            published_at=None,
            event_date=record.date_start,
            retrieved_at=datetime.now(UTC),
            geographic_scope=location,
            reliability=Confidence.HIGH,
            provenance={
                "provider": "UCDP",
                "dataset_version": self.api_version,
                "record_id": str(record.id),
                "country": record.country,
                "date_end": record.date_end.isoformat() if record.date_end else None,
                "type_of_violence": record.type_of_violence,
                "source_article": record.source_article,
                "retrieval_url": retrieval_url,
            },
        )
