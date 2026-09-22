from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from geointel.providers.runtime import validate_provider_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./geointel.db"
    model_provider: str = "offline"
    model_name_research: str = "offline-evidence-v1"
    model_name_reasoning: str = "offline-reasoning-v1"
    model_name_fast: str = "offline-fast-v1"
    ucdp_mode: str = "disabled"
    ucdp_base_url: str = "https://ucdpapi.pcr.uu.se/api"
    ucdp_api_version: str = "26.1"
    ucdp_dataset_version: str | None = None
    ucdp_endpoint_path: str | None = None
    ucdp_access_token: str | None = None
    ucdp_enabled: bool = False
    ucdp_timeout: float = 10.0
    ucdp_retries: int = 2
    views_enabled: bool = False
    views_base_url: str = ""
    views_endpoint_path: str | None = None
    views_timeout_seconds: float = 10.0
    views_max_retries: int = 2
    acled_enabled: bool = False
    acled_mode: str = "disabled"
    acled_base_url: str = "https://acleddata.com/api"
    acled_endpoint_path: str | None = None
    acled_oauth_url: str = "https://acleddata.com/oauth/token"
    acled_username: str | None = None
    acled_password: str | None = None
    acled_timeout_seconds: float = 10.0
    acled_max_retries: int = 2
    cast_enabled: bool = False
    cast_mode: str = "disabled"
    cast_base_url: str = "https://acleddata.com/api"
    cast_endpoint_path: str | None = None
    cast_timeout_seconds: float = 10.0
    cast_max_retries: int = 2
    provider_allow_private_networks: bool = False
    provider_max_pages: int = 10
    provider_max_records: int = 10_000
    provider_max_response_bytes: int = 5_000_000
    log_level: str = "INFO"

    @model_validator(mode="after")
    def validate_connectors(self):
        modes = {"official_api", "operator_adapter", "fixture", "disabled"}
        for name, mode in (
            ("UCDP", self.ucdp_mode),
            ("ACLED", self.acled_mode),
            ("CAST", self.cast_mode),
        ):
            if mode.casefold() not in modes:
                raise ValueError(f"{name}_MODE must be one of {sorted(modes)}")
        # Legacy *_ENABLED remains an adapter-mode compatibility switch.
        if self.ucdp_mode.casefold() != "disabled":
            self.ucdp_enabled = True
        if self.acled_mode.casefold() != "disabled":
            self.acled_enabled = True
        if self.cast_mode.casefold() != "disabled":
            self.cast_enabled = True
        if (
            min(
                self.ucdp_timeout,
                self.views_timeout_seconds,
                self.acled_timeout_seconds,
                self.cast_timeout_seconds,
            )
            <= 0
        ):
            raise ValueError("connector timeouts must be greater than zero")
        if (
            min(
                self.ucdp_retries,
                self.views_max_retries,
                self.acled_max_retries,
                self.cast_max_retries,
            )
            < 0
        ):
            raise ValueError("connector retries must not be negative")
        if not 1 <= self.provider_max_pages <= 100:
            raise ValueError("PROVIDER_MAX_PAGES must be between 1 and 100")
        if not 1 <= self.provider_max_records <= 100_000:
            raise ValueError("PROVIDER_MAX_RECORDS must be between 1 and 100000")
        if not 1 <= self.provider_max_response_bytes <= 20_000_000:
            raise ValueError("PROVIDER_MAX_RESPONSE_BYTES must be between 1 and 20000000")
        if self.views_enabled and (not self.views_base_url or not self.views_endpoint_path):
            raise ValueError(
                "VIEWS_BASE_URL and VIEWS_ENDPOINT_PATH are required when VIEWS_ENABLED=true"
            )
        if (
            self.acled_enabled
            and self.acled_mode.casefold() != "official_api"
            and (
                not self.acled_base_url.strip()
                or not self.acled_endpoint_path
                or not self.acled_endpoint_path.strip()
            )
        ):
            raise ValueError(
                "ACLED_BASE_URL and ACLED_ENDPOINT_PATH are required when ACLED_ENABLED=true"
            )
        if (
            self.cast_enabled
            and self.cast_mode.casefold() != "official_api"
            and (
                not self.cast_base_url.strip()
                or not self.cast_endpoint_path
                or not self.cast_endpoint_path.strip()
            )
        ):
            raise ValueError(
                "CAST_BASE_URL and CAST_ENDPOINT_PATH are required when CAST_ENABLED=true"
            )
        for name, enabled, url in (
            ("UCDP", self.ucdp_enabled, self.ucdp_base_url),
            ("VIEWS", self.views_enabled, self.views_base_url),
            ("ACLED", self.acled_enabled, self.acled_base_url),
            ("CAST", self.cast_enabled, self.cast_base_url),
        ):
            if enabled:
                try:
                    validate_provider_url(url, allow_private=self.provider_allow_private_networks)
                except ValueError as exc:
                    raise ValueError(f"unsafe {name} provider URL: {exc}") from exc
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
