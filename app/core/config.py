from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "RedLake AI"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    # Schema creation is test-only. Real environments use Alembic migrations.
    auto_create_schema: bool = False

    database_url: str = "sqlite:///./data/redlake.db"

    storage_backend: Literal["filesystem", "s3"] = "filesystem"
    storage_root: Path = Path("./data/object-store")
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key: str = "redlake"
    s3_secret_key: str = "redlake-secret"
    s3_bucket: str = "redlake-raw"

    max_upload_bytes: PositiveInt = 10 * 1024 * 1024
    allowed_origins: list[str] = Field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    return Settings()
