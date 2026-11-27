"""Application settings loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://analyzer:analyzer@localhost:5432/analyzer",
        description="SQLAlchemy async database URL.",
    )

    github_api_url: str = "https://api.github.com"
    github_token: SecretStr | None = Field(
        default=None,
        description=(
            "Optional server-side token. Raises the GitHub rate limit from 60 to 5000 "
            "requests/hour. Never required for public repositories."
        ),
    )
    github_timeout_seconds: float = Field(default=15.0, gt=0)
    github_max_retries: int = Field(default=3, ge=0, le=10)
    github_etag_cache_size: int = Field(default=512, ge=0)

    commit_window_days: int = Field(default=365, ge=7, le=3650)
    commits_max_pages: int = Field(default=5, ge=1, le=50)
    contributors_max_pages: int = Field(default=1, ge=1, le=10)
    recent_commits_limit: int = Field(default=10, ge=1, le=100)

    analysis_cache_ttl_seconds: int = Field(
        default=600,
        ge=0,
        description="Reuse a stored analysis younger than this instead of calling GitHub again.",
    )

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("github_token", mode="before")
    @classmethod
    def _empty_token_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
