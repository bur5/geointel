"""In-memory ACLED OAuth password/refresh client."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

from geointel.providers.runtime import FailureCategory, HardenedTransport, TransportError


class ACLEDAuthError(RuntimeError):
    def __init__(
        self, message: str, category: FailureCategory = FailureCategory.AUTHENTICATION_ERROR
    ):
        self.category = category
        super().__init__(message)


class ACLEDOAuthClient:
    """Caches tokens in process memory only; token values have no public representation."""

    def __init__(
        self,
        username: str,
        password: str,
        transport: HardenedTransport,
        token_url: str = "https://acleddata.com/oauth/token",
    ):
        if not username or not password:
            raise ValueError("ACLED username and password are required")
        self._username, self._password = username, password
        self._transport, self._token_url = transport, token_url
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: datetime | None = None
        self._refresh_expires_at: datetime | None = None
        self._lock = Lock()

    def access_token(self, *, force_refresh: bool = False) -> str:
        with self._lock:
            now = datetime.now(UTC)
            if (
                not force_refresh
                and self._access_token
                and self._expires_at
                and now < self._expires_at - timedelta(seconds=60)
            ):
                return self._access_token
            if self._refresh_token and self._refresh_expires_at and now < self._refresh_expires_at:
                form = {
                    "grant_type": "refresh_token",
                    "client_id": "acled",
                    "refresh_token": self._refresh_token,
                }
            else:
                form = {
                    "grant_type": "password",
                    "client_id": "acled",
                    "scope": "authenticated",
                    "username": self._username,
                    "password": self._password,
                }
            try:
                payload, _, _ = self._transport.post_form_json(self._token_url, data=form)
                self._accept(payload, now)
            except TransportError as exc:
                raise ACLEDAuthError("ACLED OAuth authentication failed", exc.category) from exc
            return self._access_token  # type: ignore[return-value]

    def _accept(self, payload: Any, now: datetime) -> None:
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("access_token"), str)
            or not payload["access_token"]
        ):
            raise ACLEDAuthError(
                "ACLED OAuth response schema mismatch", FailureCategory.SCHEMA_MISMATCH
            )
        expires = payload.get("expires_in", 86_400)
        refresh_expires = payload.get("refresh_expires_in", 1_209_600)
        if isinstance(expires, bool) or not isinstance(expires, (int, float)) or expires <= 0:
            raise ACLEDAuthError(
                "ACLED OAuth expiration is invalid", FailureCategory.SCHEMA_MISMATCH
            )
        if (
            isinstance(refresh_expires, bool)
            or not isinstance(refresh_expires, (int, float))
            or refresh_expires <= 0
        ):
            raise ACLEDAuthError(
                "ACLED OAuth refresh expiration is invalid", FailureCategory.SCHEMA_MISMATCH
            )
        self._access_token = payload["access_token"]
        self._refresh_token = (
            payload.get("refresh_token") if isinstance(payload.get("refresh_token"), str) else None
        )
        self._expires_at = now + timedelta(seconds=float(expires))
        self._refresh_expires_at = now + timedelta(seconds=float(refresh_expires))

    def safe_status(self) -> dict[str, bool]:
        return {
            "credentials_configured": True,
            "access_token_cached": self._access_token is not None,
            "tokens_persisted": False,
        }
