"""Provider operational contracts. Nothing in this module is geopolitical evidence."""

from __future__ import annotations

import ipaddress
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


class IntegrationMode(StrEnum):
    OFFICIAL_API = "OFFICIAL_API"
    OPERATOR_ADAPTER = "OPERATOR_ADAPTER"
    FIXTURE = "FIXTURE"
    DISABLED = "DISABLED"


class DocumentationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    OPERATOR_ADAPTER_REQUIRED = "OPERATOR_ADAPTER_REQUIRED"
    DISABLED_UNVERIFIED = "DISABLED_UNVERIFIED"


class FailureCategory(StrEnum):
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    PROVIDER_5XX = "PROVIDER_5XX"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    PAGINATION_ERROR = "PAGINATION_ERROR"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_PROVIDER_VERSION = "UNSUPPORTED_PROVIDER_VERSION"
    DISABLED = "DISABLED"
    RECENCY_RESTRICTED = "RECENCY_RESTRICTED"
    UNKNOWN = "UNKNOWN"


class CollectionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


@dataclass
class CollectionAudit:
    provider: str
    connector_version: str
    integration_mode: IntegrationMode
    schema_version: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    status: CollectionStatus = CollectionStatus.FAILED
    request_count: int = 0
    page_count: int = 0
    received: int = 0
    accepted: int = 0
    rejected: int = 0
    duplicates: int = 0
    truncated: bool = False
    rate_limited: bool = False
    retry_after_seconds: int | None = None
    failure_category: FailureCategory | None = None
    failure_reason: str | None = None
    rejection_reasons: list[str] = field(default_factory=list)
    provider_restrictions: dict[str, Any] = field(default_factory=dict)

    def finish(self, status: CollectionStatus) -> None:
        self.status, self.completed_at = status, datetime.now(UTC)

    def reject(self, reason: object) -> None:
        self.rejected += 1
        if len(self.rejection_reasons) < 20:
            self.rejection_reasons.append(sanitize_text(str(reason), 300))

    def public(self) -> dict[str, Any]:
        value = self.__dict__ | {
            "integration_mode": self.integration_mode.value,
            "status": self.status.value,
            "failure_category": self.failure_category.value if self.failure_category else None,
        }
        return json.loads(json.dumps(value, default=lambda x: x.isoformat()))


SECRET_KEYS = re.compile(
    r"(?i)(authorization|cookie|api[-_]?key|token|secret|signature|credential)"
)
SECRET_TEXT = re.compile(r"(?i)(bearer\s+|api[-_]?key[=:]\s*|token[=:]\s*)[^\s&,;]+")


def sanitize_url(value: str) -> str:
    parts = urlsplit(value)
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    query = [
        (key, "[REDACTED]" if SECRET_KEYS.search(key) else val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit((parts.scheme, host + port, parts.path, urlencode(query), ""))


def sanitize_text(value: str, limit: int = 500) -> str:
    return SECRET_TEXT.sub(r"\1[REDACTED]", value.replace("\x00", "�"))[:limit]


def sanitize_mapping(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "[TRUNCATED_DEPTH]"
    if isinstance(value, dict):
        return {
            str(k)[:100]: "[REDACTED]"
            if SECRET_KEYS.search(str(k))
            else sanitize_mapping(v, depth + 1)
            for k, v in list(value.items())[:100]
        }
    if isinstance(value, list):
        return [sanitize_mapping(v, depth + 1) for v in value[:100]]
    if isinstance(value, str):
        return sanitize_text(value, 2000)
    return value


def validate_provider_url(url: str, *, allow_private: bool = False) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("provider URL must be HTTPS, absolute, and contain no credentials")
    host = parts.hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("local provider URL requires explicit private-network opt-in")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not allow_private and not address.is_global:
        raise ValueError("non-public provider address requires explicit private-network opt-in")
    return url.rstrip("/")


class TransportError(RuntimeError):
    def __init__(
        self,
        category: FailureCategory,
        message: str,
        *,
        retry_after_seconds: int | None = None,
        request_count: int | None = None,
    ):
        self.category = category
        self.retry_after_seconds = retry_after_seconds
        self.request_count = request_count
        super().__init__(sanitize_text(message))


MAX_RETRY_AFTER_SECONDS = 3600


def parse_retry_after(value: str | None) -> int | None:
    """Parse delay-seconds conservatively and cap untrusted upstream advice."""
    if value is None or not value.isascii() or not value.isdigit():
        return None
    try:
        seconds = int(value)
    except ValueError:  # Defensive for unexpectedly large integer strings.
        return None
    return min(seconds, MAX_RETRY_AFTER_SECONDS)


class HardenedTransport:
    """Bounded JSON GET transport; redirects are deliberately disabled."""

    def __init__(
        self,
        *,
        timeout: float = 10,
        retries: int = 2,
        max_bytes: int = 5_000_000,
        allow_private: bool = False,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not 0 < timeout <= 120 or not 0 <= retries <= 5 or not 1 <= max_bytes <= 20_000_000:
            raise ValueError("transport bounds are invalid")
        self.timeout, self.retries, self.max_bytes = timeout, retries, max_bytes
        self.allow_private, self.client, self.sleep = allow_private, client, sleep

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry_rate_limited: bool = True,
    ) -> tuple[Any, str, int]:
        validate_provider_url(url, allow_private=self.allow_private)
        owned = self.client is None
        client = self.client or httpx.Client(
            timeout=httpx.Timeout(self.timeout), follow_redirects=False
        )
        try:
            for attempt in range(self.retries + 1):
                try:
                    response = client.get(url, params=params, headers=headers, timeout=self.timeout)
                    if response.is_redirect:
                        raise TransportError(
                            FailureCategory.INVALID_RESPONSE, "provider redirects are forbidden"
                        )
                    if response.status_code in {401, 403}:
                        category = (
                            FailureCategory.AUTHENTICATION_ERROR
                            if response.status_code == 401
                            else FailureCategory.AUTHORIZATION_ERROR
                        )
                        raise TransportError(
                            category, f"provider returned HTTP {response.status_code}"
                        )
                    retry_after_seconds = parse_retry_after(response.headers.get("Retry-After"))
                    retryable = (
                        response.status_code == 408
                        or response.status_code >= 500
                        or (response.status_code == 429 and retry_rate_limited)
                    )
                    if retryable and attempt < self.retries:
                        delay = min(2.0, 0.05 * (2**attempt))
                        if retry_after_seconds is not None:
                            delay = min(2.0, float(retry_after_seconds))
                        self.sleep(delay)
                        continue
                    if response.status_code == 429:
                        raise TransportError(
                            FailureCategory.RATE_LIMITED,
                            "provider rate limited collection",
                            retry_after_seconds=retry_after_seconds,
                            request_count=attempt + 1,
                        )
                    if response.status_code >= 500:
                        raise TransportError(
                            FailureCategory.PROVIDER_5XX,
                            f"provider returned HTTP {response.status_code}",
                        )
                    if response.status_code >= 400:
                        raise TransportError(
                            FailureCategory.INVALID_RESPONSE,
                            f"provider returned HTTP {response.status_code}",
                        )
                    if len(response.content) > self.max_bytes:
                        raise TransportError(
                            FailureCategory.PAYLOAD_TOO_LARGE,
                            "provider response exceeds configured maximum",
                        )
                    content_type = (
                        response.headers.get("content-type", "application/json")
                        .split(";", 1)[0]
                        .strip()
                    )
                    if content_type not in {"application/json", "application/problem+json"}:
                        raise TransportError(
                            FailureCategory.INVALID_RESPONSE, "provider response is not JSON"
                        )
                    try:
                        return response.json(), sanitize_url(str(response.request.url)), attempt + 1
                    except ValueError as exc:
                        raise TransportError(
                            FailureCategory.INVALID_RESPONSE, "provider returned malformed JSON"
                        ) from exc
                except httpx.TimeoutException as exc:
                    if attempt == self.retries:
                        raise TransportError(FailureCategory.TIMEOUT, str(exc)) from exc
                except httpx.TransportError as exc:
                    if attempt == self.retries:
                        raise TransportError(FailureCategory.NETWORK_ERROR, str(exc)) from exc
            raise TransportError(FailureCategory.UNKNOWN, "bounded transport exhausted")
        finally:
            if owned:
                client.close()

    def post_form_json(
        self,
        url: str,
        *,
        data: dict[str, str],
    ) -> tuple[Any, str, int]:
        """POST a bounded form and return JSON without ever retaining form secrets."""
        validate_provider_url(url, allow_private=self.allow_private)
        owned = self.client is None
        client = self.client or httpx.Client(
            timeout=httpx.Timeout(self.timeout), follow_redirects=False
        )
        try:
            for attempt in range(self.retries + 1):
                try:
                    response = client.post(url, data=data, timeout=self.timeout)
                    if response.is_redirect:
                        raise TransportError(
                            FailureCategory.INVALID_RESPONSE, "provider redirects are forbidden"
                        )
                    if response.status_code in {400, 401}:
                        raise TransportError(
                            FailureCategory.AUTHENTICATION_ERROR,
                            f"provider authentication failed (HTTP {response.status_code})",
                        )
                    if response.status_code == 403:
                        raise TransportError(
                            FailureCategory.AUTHORIZATION_ERROR,
                            "provider authorization failed (HTTP 403)",
                        )
                    retryable = response.status_code in {408, 429} or response.status_code >= 500
                    if retryable and attempt < self.retries:
                        self.sleep(min(2.0, 0.05 * (2**attempt)))
                        continue
                    if response.status_code == 429:
                        raise TransportError(FailureCategory.RATE_LIMITED, "provider rate limited")
                    if response.status_code >= 500:
                        raise TransportError(
                            FailureCategory.PROVIDER_5XX,
                            f"provider returned HTTP {response.status_code}",
                        )
                    if response.status_code >= 400:
                        raise TransportError(
                            FailureCategory.INVALID_RESPONSE,
                            f"provider returned HTTP {response.status_code}",
                        )
                    if len(response.content) > self.max_bytes:
                        raise TransportError(
                            FailureCategory.PAYLOAD_TOO_LARGE, "provider response is too large"
                        )
                    try:
                        return response.json(), sanitize_url(str(response.request.url)), attempt + 1
                    except ValueError as exc:
                        raise TransportError(
                            FailureCategory.INVALID_RESPONSE, "provider returned malformed JSON"
                        ) from exc
                except httpx.TimeoutException as exc:
                    if attempt == self.retries:
                        raise TransportError(FailureCategory.TIMEOUT, str(exc)) from exc
                except httpx.TransportError as exc:
                    if attempt == self.retries:
                        raise TransportError(FailureCategory.NETWORK_ERROR, str(exc)) from exc
            raise TransportError(FailureCategory.UNKNOWN, "bounded transport exhausted")
        finally:
            if owned:
                client.close()


def paginate(
    fetch: Callable[[str | None], tuple[list[dict[str, Any]], str | None]],
    *,
    identity: Callable[[dict[str, Any]], str],
    audit: CollectionAudit,
    max_pages: int = 10,
    max_records: int = 10_000,
) -> list[dict[str, Any]]:
    """Paginate only an explicitly documented adapter cursor contract."""
    if not 1 <= max_pages <= 100 or not 1 <= max_records <= 100_000:
        raise ValueError("pagination bounds are invalid")
    cursor, seen_cursors, output, identities = None, set(), [], set()
    for _ in range(max_pages):
        try:
            records, next_cursor = fetch(cursor)
        except Exception as exc:
            audit.failure_category = getattr(exc, "category", FailureCategory.PAGINATION_ERROR)
            audit.failure_reason = sanitize_text(str(exc))
            audit.finish(CollectionStatus.PARTIAL if output else CollectionStatus.FAILED)
            return output
        audit.request_count += 1
        audit.page_count += 1
        audit.received += len(records)
        for record in records:
            try:
                record_id = identity(record)
                if record_id in identities:
                    audit.duplicates += 1
                    continue
                identities.add(record_id)
                output.append(record)
                audit.accepted += 1
            except Exception as exc:
                audit.reject(exc)
            if len(output) >= max_records:
                audit.truncated = True
                audit.finish(CollectionStatus.PARTIAL)
                return output
        if not records or next_cursor is None:
            audit.finish(
                CollectionStatus.SUCCEEDED if not audit.rejected else CollectionStatus.PARTIAL
            )
            return output
        if (
            not isinstance(next_cursor, str)
            or not next_cursor
            or len(next_cursor) > 500
            or next_cursor in seen_cursors
        ):
            audit.failure_category = FailureCategory.PAGINATION_ERROR
            audit.failure_reason = "invalid or repeated pagination cursor"
            audit.finish(CollectionStatus.PARTIAL if output else CollectionStatus.FAILED)
            return output
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    audit.truncated = True
    audit.finish(CollectionStatus.PARTIAL)
    return output
