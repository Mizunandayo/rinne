"""Environment configuration for the Rinne agent service."""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import Literal

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Field names map case-insenitively to env var names."""

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    port: int = Field(default=8080, ge=1, le=65535)
    host: str = "0.0.0.0"  # noqa: S104 - binding all interfaces is required inside a container

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    service_version: str = Field(default="0.0.0-dev", min_length=1, max_length=64)
    gcp_project_id: str = Field(default="rinnehackathon", min_length=6, max_length=30)
    gcp_region: str = Field(default="asia-southeast1", min_length=1, max_length=32)

    # Set by Cloud Run
    k_revision: str | None = Field(default=None, max_length=128)
    k_service: str | None = Field(default=None, max_length=128)

    # OpenAPI/Swagger. Off in production this service is IAM-Private
    enable_docs: bool = False

    # Starlette has no built-in body cap. middleware.py enforeces this one.
    max_request_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    @field_validator("app_env")
    @classmethod
    def _docs_off_in_production(cls, value: str) -> str:
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def docs_enabled(self) -> bool:
        return self.enable_docs and not self.is_production


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build and cache settings. Exits the process on invalid configuration."""
    try:
        return Settings()
    except ValidationError as exc:
        # Print field names and messages, never values.
        lines = [
            f"  - {'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in exc.errors()
        ]
        sys.stderr.write(
            "services/agent: invalid environment. Refusing to start.\n"
            + "\n".join(lines)
            + "\nSee .env.example for the full set.\n"
        )
        raise SystemExit(1) from exc
