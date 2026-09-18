from functools import lru_cache
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
    ucdp_access_token: str | None = None
    ucdp_enabled: bool = False
    log_level: str = "INFO"

@lru_cache
def get_settings() -> Settings:
    return Settings()
