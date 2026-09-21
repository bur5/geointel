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
    log_level: str = "INFO"

    @model_validator(mode="after")
    def validate_connectors(self):
        if self.ucdp_timeout <= 0 or self.views_timeout_seconds <= 0:
            raise ValueError("connector timeouts must be greater than zero")
        if self.ucdp_retries < 0 or self.views_max_retries < 0:
            raise ValueError("connector retries must not be negative")
        if self.views_enabled and (not self.views_base_url or not self.views_endpoint_path):
            raise ValueError(
                "VIEWS_BASE_URL and VIEWS_ENDPOINT_PATH are required when VIEWS_ENABLED=true"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
