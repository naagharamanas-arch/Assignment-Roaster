"""Application settings loaded from environment variables."""

import logging
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_PLACEHOLDER_SECRET_MARKERS = ("change-me", "changeme", "your-secret-key")
_DEV_ENVIRONMENTS = {"dev", "development", "test", "testing", "local"}


class Settings(BaseSettings):
    """Typed settings; every field has a safe default so imports work without a .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+psycopg://user:password@localhost:5432/assignment_roaster"
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = ""
    GITHUB_TOKEN: str = ""

    DODO_API_KEY: str = ""
    DODO_WEBHOOK_SECRET: str = ""

    APP_BASE_URL: str = "http://localhost:5173"

    API_BASE_URL: str = "http://localhost:8000"

    DAILY_ROAST_LIMIT: int = 3
    GLOBAL_DAILY_JOB_CAP: int = 200
    PIPELINE_CONCURRENCY: int = 3
    PIPELINE_TIMEOUT_SECONDS: int = 300
    STALE_JOB_MINUTES: int = 10
    OPENAI_TIMEOUT_SECONDS: int = 60
    ANALYSIS_MAX_COMPLETION_TOKENS: int = 4000
    ROAST_MAX_COMPLETION_TOKENS: int = 4000
    MAX_FILES: int = 25
    MAX_BYTES: int = 150000

    @property
    def is_dev(self) -> bool:
        """True for local development and test environments."""
        return self.ENVIRONMENT.lower() in _DEV_ENVIRONMENTS

    @field_validator("DATABASE_URL")
    @classmethod
    def _use_psycopg3_driver(cls, value: str) -> str:
        """Only psycopg 3 is installed, so map bare postgres schemes onto it."""
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @field_validator("ALGORITHM")
    @classmethod
    def _only_hs256(cls, value: str) -> str:
        """Refuse algorithm downgrades such as 'none'."""
        if value != "HS256":
            raise ValueError("ALGORITHM must be HS256")
        return value

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        """Fail fast outside development if the signing key is a placeholder or too short."""
        if self.ENVIRONMENT.lower() in _DEV_ENVIRONMENTS:
            return self
        key = self.SECRET_KEY.lower()
        if len(self.SECRET_KEY) < 32 or any(m in key for m in _PLACEHOLDER_SECRET_MARKERS):
            raise ValueError(
                "SECRET_KEY must be a random value of at least 32 characters when "
                "ENVIRONMENT is not development (generate one with: openssl rand -hex 32)"
            )
        if not self.GITHUB_TOKEN:
            logger.warning("GITHUB_TOKEN is not set: GitHub allows only 60 requests/hour per IP")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance."""
    return Settings()


settings = get_settings()
