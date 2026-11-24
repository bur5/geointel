import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from geointel.domain.schemas import NormalizedForecastSignal, reject_boolean_prediction
from geointel.providers.runtime import sanitize_mapping, sanitize_url


class VIEWSError(RuntimeError):
    pass


class VIEWSRawForecast(BaseModel):
    """Validated GEOINTEL adapter contract, not a claim about a public VIEWS API schema."""

    id: str | int
    model: str = Field(max_length=150)
    model_version: str | None = Field(default=None, max_length=100)
    geographic_unit: str = Field(max_length=80)
    location: str = Field(max_length=200)
    issue_date: datetime
    target_start: datetime
    target_end: datetime
    horizon_months: int | None = Field(default=None, ge=1)
    target_variable: str = Field(max_length=200)
    prediction: float
    _reject_boolean = field_validator("prediction", mode="before")(reject_boolean_prediction)
    unit: str | None = Field(default=None, max_length=80)
    scale: str | None = Field(default=None, max_length=120)


class VIEWSConnector:
    """Fetch VIEWS forecasts only from an operator-supplied, verified adapter endpoint."""

    connector_name = "VIEWS"

    def __init__(
        self,
        base_url: str,
        endpoint_path: str | None,
        timeout: float = 10,
        retries: int = 2,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if retries < 0:
            raise ValueError("retries must not be negative")
        if endpoint_path and not base_url.strip():
            raise ValueError("base_url is required when endpoint_path is configured")
        self.base_url = base_url.rstrip("/")
        self.endpoint_path = endpoint_path
        self.timeout = timeout
        self.retries = retries
        self._client = client
        self._sleep = sleep

    def collect(self, location: str, horizon_months: int = 12) -> list[NormalizedForecastSignal]:
        if not self.endpoint_path:
            raise VIEWSError(
                "VIEWS endpoint path is not configured; provide a verified adapter endpoint"
            )
        if self._client is not None:
            return self._collect(self._client, location, horizon_months)
        with httpx.Client(timeout=self.timeout) as client:
            return self._collect(client, location, horizon_months)

    def _collect(
        self, client: httpx.Client, location: str, horizon_months: int
    ) -> list[NormalizedForecastSignal]:
        url = f"{self.base_url}/{self.endpoint_path.lstrip('/')}"
        last: Exception | None = None
        attempts_used = 0
        for attempt in range(self.retries + 1):
            attempts_used = attempt + 1
            try:
                response = client.get(
                    url,
                    params={"location": location},
                    timeout=self.timeout,
                )
                if self._is_transient(response.status_code):
                    raise httpx.HTTPStatusError(
                        "transient VIEWS response", request=response.request, response=response
                    )
                response.raise_for_status()
                if len(response.content) > 5_000_000:
                    raise ValueError("VIEWS adapter response exceeds 5 MB")
                return [
                    self.normalize(raw, location, horizon_months, str(response.request.url))
                    for raw in self._records(response.json())
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
        raise VIEWSError(f"VIEWS retrieval failed after {attempts_used} attempts: {last}") from last

    @staticmethod
    def _is_transient(status_code: int) -> bool:
        return status_code in {408, 429} or status_code >= 500

    @staticmethod
    def _records(payload: Any) -> list[dict]:
        if not isinstance(payload, dict) or set(payload) != {"forecasts"}:
            raise ValueError("VIEWS adapter response must contain only a forecasts list")
        records = payload["forecasts"]
        if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
            raise ValueError("VIEWS adapter forecasts must be a list of objects")
        if len(records) > 10_000:
            raise ValueError("VIEWS adapter response exceeds 10000 records")
        return records

    def normalize(
        self,
        raw: dict,
        requested_location: str,
        requested_horizon_months: int,
        retrieval_url: str | None = None,
    ) -> NormalizedForecastSignal:
        record = VIEWSRawForecast.model_validate(raw)
        if len(str(record.id)) > 200:
            raise ValueError("VIEWS record id exceeds 200 characters")
        notes = []
        if record.location.casefold() != requested_location.casefold():
            notes.append(
                f"location mismatch: requested {requested_location}, received {record.location}"
            )
        if record.geographic_unit.casefold() != "country":
            notes.append(f"geographic mismatch: {record.geographic_unit} output was not aggregated")
        if record.horizon_months != requested_horizon_months:
            received_horizon = record.horizon_months or "unspecified"
            notes.append(
                "horizon mismatch: requested "
                f"{requested_horizon_months} months, received {received_horizon}"
            )
        return NormalizedForecastSignal(
            source_record_id=str(record.id),
            model_name=record.model,
            model_version=record.model_version,
            geographic_unit=record.geographic_unit,
            location=record.location,
            issue_date=record.issue_date,
            target_start=record.target_start,
            target_end=record.target_end,
            horizon_months=record.horizon_months,
            target_variable=record.target_variable,
            prediction=record.prediction,
            unit=record.unit,
            scale=record.scale,
            retrieved_at=datetime.now(UTC),
            source_url=sanitize_url(retrieval_url) if retrieval_url else None,
            alignment_status="mismatch" if notes else "aligned",
            alignment_notes=notes,
            provenance={
                "provider": "VIEWS",
                "record_id": str(record.id),
                "model": record.model,
                "model_version": record.model_version,
                "retrieval_url": sanitize_url(retrieval_url) if retrieval_url else None,
                "schema": "geointel-views-adapter-v1",
                "predictive_not_observed": True,
                "raw_adapter_record": sanitize_mapping(record.model_dump(mode="json")),
            },
        )

    model_config = ConfigDict(extra="forbid")
