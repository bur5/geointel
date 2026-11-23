from __future__ import annotations

from calendar import month_name, monthrange
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from geointel.connectors.views import VIEWSConnector, VIEWSError
from geointel.coverage import Scope
from geointel.domain.schemas import NormalizedForecastSignal
from geointel.providers.acled_auth import ACLEDOAuthClient
from geointel.providers.runtime import (
    CollectionAudit,
    CollectionStatus,
    HardenedTransport,
    IntegrationMode,
    paginate,
    sanitize_mapping,
    sanitize_url,
)


class CASTError(VIEWSError):
    pass


class CASTRawForecast(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country: str = Field(max_length=120)
    admin1: str | None = Field(default=None, max_length=160)
    month: str = Field(min_length=3, max_length=20)
    year: int = Field(ge=2000, le=2200)
    total_forecast: float | None = Field(default=None, ge=0)
    battles_forecast: float | None = Field(default=None, ge=0)
    erv_forecast: float | None = Field(default=None, ge=0)
    vac_forecast: float | None = Field(default=None, ge=0)
    total_observed: float | None = Field(default=None, ge=0)
    battles_observed: float | None = Field(default=None, ge=0)
    erv_observed: float | None = Field(default=None, ge=0)
    vac_observed: float | None = Field(default=None, ge=0)
    timestamp: int | datetime


class CASTConnector(VIEWSConnector):
    """CAST official event-count forecasts; never observational Event records."""

    connector_name = "CAST"

    def __init__(
        self,
        *args,
        official_api: bool = False,
        oauth: ACLEDOAuthClient | None = None,
        transport: HardenedTransport | None = None,
        max_pages: int = 10,
        max_records: int = 10_000,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.official_api, self.oauth = official_api, oauth
        self.transport = transport or HardenedTransport(
            timeout=self.timeout, retries=self.retries, client=self._client, sleep=self._sleep
        )
        self.max_pages, self.max_records = max_pages, max_records
        self.last_audit: CollectionAudit | None = None

    def collect(self, location: str, horizon_months: int = 12) -> list[NormalizedForecastSignal]:
        if self.official_api:
            return self._collect_official(location, horizon_months)
        if not self.endpoint_path:
            raise CASTError("CAST verified adapter endpoint is not configured")
        try:
            return super().collect(location, horizon_months)
        except VIEWSError as exc:
            raise CASTError(str(exc).replace("VIEWS", "CAST")) from exc

    def _collect_official(
        self, location: str, horizon_months: int
    ) -> list[NormalizedForecastSignal]:
        if not self.oauth:
            raise CASTError("CAST ACLED OAuth client is not configured")
        audit = CollectionAudit(
            "CAST", "0.1.2", IntegrationMode.OFFICIAL_API, "acled-cast-official-v1"
        )
        self.last_audit = audit
        audit.query_scope = Scope(kind="forecast", geography=location)
        retrieval_urls: dict[str, str] = {}

        def fetch(cursor):
            payload, retrieval_url, _ = self.transport.get_json(
                f"{self.base_url}/cast/read",
                params={"country": location, "cursor": "0" if cursor is None else cursor},
                headers={
                    "Authorization": f"Bearer {self.oauth.access_token()}",
                    "Accept": "application/json",
                },
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ValueError("CAST response schema mismatch")
            rows = payload["data"]
            if not all(isinstance(row, dict) for row in rows):
                raise ValueError("CAST data contains a non-object")
            if "next_cursor" not in payload:
                audit.pagination_ambiguous = True
            next_cursor = payload.get("next_cursor")
            if isinstance(next_cursor, bool) or (
                next_cursor is not None and not isinstance(next_cursor, (str, int))
            ):
                raise ValueError("CAST next_cursor is malformed")
            for row in rows:
                try:
                    retrieval_urls.setdefault(self._row_identity(row), retrieval_url)
                except KeyError:
                    continue
            return rows, None if next_cursor is None else str(next_cursor)

        rows = paginate(
            fetch,
            identity=lambda row: self._row_identity(row),
            audit=audit,
            initial_cursor="0",
            max_pages=self.max_pages,
            max_records=self.max_records,
        )
        signals = []
        for raw in rows:
            try:
                signals.extend(
                    self.normalize_official(
                        raw, location, horizon_months, retrieval_urls[self._row_identity(raw)]
                    )
                )
            except (ValidationError, ValueError, TypeError) as exc:
                audit.reject(exc)
        if len(signals) > self.max_records:
            signals = signals[: self.max_records]
            audit.truncated = True
        if (audit.rejected or audit.truncated) and audit.status == CollectionStatus.SUCCEEDED:
            audit.finish(CollectionStatus.PARTIAL)
        if not rows and audit.failure_category:
            error = CASTError(f"CAST collection failed: {audit.failure_reason}")
            error.category = audit.failure_category
            raise error
        return signals

    @staticmethod
    def _row_identity(raw: dict[str, Any]) -> str:
        return f"{raw['country']}|{raw.get('admin1') or ''}|{raw['year']}|{raw['month']}"

    def normalize_official(
        self,
        raw: dict,
        requested_location: str,
        requested_horizon_months: int,
        retrieval_url: str | None = None,
    ) -> list[NormalizedForecastSignal]:
        record = CASTRawForecast.model_validate(raw)
        try:
            month = next(
                index
                for index, name in enumerate(month_name)
                if name and name.casefold() == record.month.strip().casefold()
            )
        except StopIteration as exc:
            raise ValueError(f"CAST month is invalid: {record.month!r}") from exc
        provider_timestamp = (
            datetime.fromtimestamp(record.timestamp, tz=UTC)
            if isinstance(record.timestamp, int)
            else record.timestamp.astimezone(UTC)
        )
        start = datetime(record.year, month, 1, tzinfo=UTC)
        end = datetime(
            record.year,
            month,
            monthrange(record.year, month)[1],
            23,
            59,
            59,
            tzinfo=UTC,
        )
        geography = "admin1" if record.admin1 else "country"
        location = record.admin1 or record.country
        observed = {
            "total": record.total_observed,
            "battles": record.battles_observed,
            "erv": record.erv_observed,
            "vac": record.vac_observed,
        }
        targets = {
            "total_events": record.total_forecast,
            "battles": record.battles_forecast,
            "explosions_remote_violence": record.erv_forecast,
            "violence_against_civilians": record.vac_forecast,
        }
        retrieved_at = datetime.now(UTC)
        temporal_classification = (
            "historical_forecast" if end < retrieved_at else "current_or_future_forecast"
        )
        output = []
        for target, value in targets.items():
            if value is None:
                continue
            identity = self._row_identity(raw) + f"|{target}"
            notes = []
            if record.country.casefold() != requested_location.casefold():
                notes.append(
                    f"location mismatch: requested {requested_location}, received {record.country}"
                )
            if temporal_classification == "historical_forecast":
                notes.append(
                    "temporal mismatch: CAST forecast target period ended before retrieval; "
                    "retain for historical/backtesting use, not current operational forecasting"
                )
            output.append(
                NormalizedForecastSignal(
                    provider="CAST",
                    source_record_id=identity,
                    model_name="ACLED CAST",
                    model_version=None,
                    geographic_unit=geography,
                    location=location,
                    issue_date=provider_timestamp,
                    target_start=start,
                    target_end=end,
                    horizon_months=None,
                    target_variable=target,
                    prediction=value,
                    unit="forecast_event_count",
                    scale="monthly",
                    retrieved_at=retrieved_at,
                    source_url=sanitize_url(retrieval_url) if retrieval_url else None,
                    alignment_status="mismatch" if notes else "aligned",
                    alignment_notes=notes,
                    provenance={
                        "provider": "CAST",
                        "endpoint": "cast",
                        "record_id": identity,
                        "provider_timestamp": provider_timestamp.isoformat(),
                        "forecast_type": target,
                        "native_unit": "forecast_event_count",
                        "observed_context": sanitize_mapping(observed),
                        "forecast_and_observed_are_distinct": True,
                        "predictive_not_observed": True,
                        "requested_horizon_months": requested_horizon_months,
                        "temporal_classification": temporal_classification,
                        "current_operational_signal": (
                            temporal_classification != "historical_forecast"
                        ),
                        "retrieval_url": sanitize_url(retrieval_url) if retrieval_url else None,
                        "retrieved_at": retrieved_at.isoformat(),
                        "schema": "geointel-cast-official-v1",
                    },
                )
            )
        return output

    def normalize(
        self,
        raw: dict,
        requested_location: str,
        requested_horizon_months: int,
        retrieval_url: str | None = None,
    ) -> NormalizedForecastSignal:
        signal = super().normalize(raw, requested_location, requested_horizon_months, retrieval_url)
        signal.provider = "CAST"
        signal.provenance.update(
            provider="CAST", schema="geointel-cast-adapter-v1", predictive_not_observed=True
        )
        return signal
