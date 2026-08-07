"""Application configuration via environment variables (12-factor)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values come from the environment or .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "FleetPulse"
    debug: bool = False

    # Phase 1: postgresql+psycopg://... — required once the data layer lands.
    database_url: str | None = None
    # Phase 5: LLM summariser / Phase 7: Ops Agent.
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
