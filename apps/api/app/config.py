"""Application configuration.

Settings are loaded from environment variables (see /.env.example at the
repo root). Never read os.environ directly elsewhere in the app — depend on
`get_settings()` so configuration stays centralized and testable.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "staging", "production"] = "development"

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Comma-separated list of allowed CORS origins.
    cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://caseflow:caseflow@localhost:5432/caseflow"
    redis_url: str = "redis://localhost:6379/0"

    oauth_client_id: str = ""
    oauth_client_secret: str = ""

    openai_api_key: str = ""

    aws_region: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_bucket: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Tests override via dependency_overrides."""
    return Settings()
