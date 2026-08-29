"""Environment configuration for the Rinne agent service."""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOOP_CEILING = 6


class Settings(BaseSettings):
    """Runtime settings. Field names map case-insensitively to env var names."""

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

    # Ingest
    scan_bucket: str = Field(default="rinne-scans-rinnehackathon", min_length=3, max_length=63)
    scan_prefix: str = Field(default="scan-queue/", min_length=1, max_length=128)
    max_scan_bytes: int = Field(default=6_291_456, ge=1024, le=26_214_400)
    object_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    # object_mode=memory is the test path, chosen the same way store_mode and
    # triage_mode are: by configuration, never by a runtime fallback.
    object_mode: Literal["gcs", "memory"] = "gcs"

    # Loop bound (section 12)
    max_attempts: int = Field(default=3, ge=1, le=_LOOP_CEILING)

    # Firestore
    store_mode: Literal["firestore", "memory"] = "firestore"
    firestore_database: str = Field(default="(default)", min_length=1, max_length=64)
    firestore_collection: str = Field(default="agent-jobs", min_length=1, max_length=64)
    firestore_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    firestore_max_attempts: int = Field(default=3, ge=1, le=6)
    firestore_backoff_seconds: float = Field(default=0.5, ge=0, le=10)

    # -- Vertex AI, tier 1
    triage_mode: Literal["flash", "stub"] = "flash"
    vertex_location: str = Field(default="asia-southeast1", min_length=1, max_length=32)
    triage_model: str = Field(default="gemini-3.5-flash", min_length=1, max_length=64)
    triage_temperature: float = Field(default=0.0, ge=0, le=2)
    triage_max_output_tokens: int = Field(default=512, ge=64, le=8192)

    triage_thinking_budget: int = Field(default=0, ge=0, le=24576)
    triage_timeout_seconds: float = Field(default=60.0, gt=0, le=300)

    @model_validator(mode="after")
    def _prefix_is_a_prefix(self) -> Self:
        if self.scan_prefix.startswith("/") or ".." in self.scan_prefix:
            raise ValueError("scan_prefix must be a relative object prefix without traversal")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def docs_enabled(self) -> bool:
        return self.enable_docs and not self.is_production

    @property
    def is_cloud_run(self) -> bool:
        """K_SERVICE is set by Cloud Run and by nothing else."""
        return bool(self.k_service)


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
