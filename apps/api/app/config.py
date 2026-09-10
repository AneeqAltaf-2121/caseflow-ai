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
    oauth_redirect_url: str = "http://localhost:8000/auth/google/callback"

    # Signs/verifies session JWTs (see app/auth/jwt.py). Must be overridden
    # with a long random value outside development — see .env.example.
    jwt_secret_key: str = "dev-insecure-secret-change-me-before-deploying"
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_minutes: int = 60
    jwt_refresh_token_ttl_days: int = 30

    # The mock OAuth provider lets local dev/tests log in as any email
    # without a real IdP. It's wired in regardless of environment, but
    # routes refuse to use it outside development/test — see
    # app/auth/providers.py.
    allow_mock_oauth: bool = True

    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # LLM/embedding provider selection. "mock" needs no API key and is the
    # default so the app runs end-to-end without any provider credentials —
    # see app/integrations/llm.py and app/integrations/embeddings.py.
    llm_provider: Literal["mock", "anthropic", "openai"] = "mock"
    embedding_provider: Literal["mock", "local", "openai"] = "mock"
    embedding_dimensions: int = 384

    aws_region: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_bucket: str = ""
    s3_endpoint_url: str = ""  # set for local MinIO / S3-compatible dev storage

    # "local" writes to ./storage on disk (dev default, no AWS needed);
    # "s3" uses the s3_* settings above. See app/integrations/storage.py.
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_path: str = "./storage"
    max_upload_size_mb: int = 50

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
