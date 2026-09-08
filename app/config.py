"""Application configuration via environment variables (12-factor)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values come from the environment or .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "FleetPulse"
    debug: bool = False

    # Default matches docker-compose for zero-friction local dev; prod overrides.
    database_url: str = "postgresql+psycopg://fleetpulse:fleetpulse@localhost:5432/fleetpulse"
    # Phase 5: LLM summariser / Phase 7: Ops Agent.
    anthropic_api_key: str = ""
    fleetpulse_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
