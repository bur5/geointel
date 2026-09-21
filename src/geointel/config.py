from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./geointel.db"
    model_provider: str = "offline"
    model_name_research: str = "offline-evidence-v1"
    model_name_reasoning: str = "offline-reasoning-v1"
    model_name_fast: str = "offline-fast-v1"
    ucdp_base_url: str = "https://ucdpapi.pcr.uu.se"
    ucdp_api_version: str = "24.1"
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
    acled_base_url: str = ""
    acled_endpoint_path: str | None = None
    acled_timeout_seconds: float = 10.0
    acled_max_retries: int = 2
    cast_enabled: bool = False
    cast_base_url: str = ""
    cast_endpoint_path: str | None = None
    cast_timeout_seconds: float = 10.0
    cast_max_retries: int = 2
    log_level: str = "INFO"

    @model_validator(mode="after")
    def validate_connectors(self):
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
        if self.views_enabled and (not self.views_base_url or not self.views_endpoint_path):
            raise ValueError(
                "VIEWS_BASE_URL and VIEWS_ENDPOINT_PATH are required when VIEWS_ENABLED=true"
            )
        if self.acled_enabled and (
            not self.acled_base_url.strip()
            or not self.acled_endpoint_path
            or not self.acled_endpoint_path.strip()
        ):
            raise ValueError(
                "ACLED_BASE_URL and ACLED_ENDPOINT_PATH are required when ACLED_ENABLED=true"
            )
        if self.cast_enabled and (
            not self.cast_base_url.strip()
            or not self.cast_endpoint_path
            or not self.cast_endpoint_path.strip()
        ):
            raise ValueError(
                "CAST_BASE_URL and CAST_ENDPOINT_PATH are required when CAST_ENABLED=true"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
