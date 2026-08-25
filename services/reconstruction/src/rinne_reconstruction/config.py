"""Environment configuration for the Rinne reconstruction service."""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Confidence components are rounded to 4dp, so the weights are compared at 4dp
# too. Anything finer is comparing float noise.
_WEIGHT_PRECISION = 4


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

    # OpenAPI/Swagger. Off in production - this service is IAM-private.
    enable_docs: bool = False

    # -- Request limits ------------------------------------------------
    # 25 MiB, under Cloud Run's 32 MiB request ceiling. Starlette has no
    # built-in body cap;
    max_request_bytes: int = Field(default=26_214_400, ge=1024, le=33_554_432)
    max_metadata_chars: int = Field(default=4096, ge=0, le=65_536)
    max_images: int = Field(default=4, ge=1, le=8)
    max_image_bytes: int = Field(default=6_291_456, ge=1024, le=26_214_400)
    max_image_pixels: int = Field(default=40_000_000, ge=1, le=200_000_000)
    max_image_edge: int = Field(default=1536, ge=64, le=8192)
    request_timeout_seconds: float = Field(default=300.0, gt=0, le=900)

    # -- Mesh normalisation --------------------------------------------
    assumed_longest_dimension_meters: float = Field(default=0.30, gt=0, le=5)
    # Solid-versus-shell discount in the mass estimate. A documented guess.
    # Day 8's refit replaces it with a measurement.
    solid_fraction: float = Field(default=0.55, gt=0, le=1)

    # -- Confidence ----------------------------------------------------
    # Day 2 ships THREE components. The full weights are 0.45 / 0.30 / 0.15 /
    # 0.10; with foregroundQuality absent the remaining three are rescaled to
    confidence_weight_field_decisiveness: float = Field(default=0.5294, ge=0, le=1)
    confidence_weight_watertightness: float = Field(default=0.3529, ge=0, le=1)
    confidence_weight_volume_plausibility: float = Field(default=0.1177, ge=0, le=1)

    ambiguity_band_ratio: float = Field(default=0.15, gt=0, le=1)
    ambiguity_reference: float = Field(default=0.10, gt=0, le=1)

    # UNCALIBRATED. These two thresholds are documented guesses until Day 3
    confidence_band_low_max: float = Field(default=0.45, ge=0, le=1)
    confidence_band_high_min: float = Field(default=0.70, ge=0, le=1)
    confidence_calibrated: bool = False

    # Below this face count there is nothing there to be confident about, so
    min_faces: int = Field(default=100, ge=0, le=100_000)

    # -- Pipeline ------------------------------------------------------
    pipeline_name: Literal["stub", "triposr"] = "stub"
    stub_resolution: int = Field(default=64, ge=16, le=192)

    # -- Storage -------------------------------------------------------
    storage_mode: Literal["gcs", "memory"] = "gcs"
    gcs_bucket: str = Field(default="rinne-artifacts-rinnehackathon", min_length=3, max_length=63)
    gcs_object_prefix: str = Field(default="meshes", min_length=1, max_length=64)
    upload_max_attempts: int = Field(default=3, ge=1, le=6)
    upload_backoff_seconds: float = Field(default=0.5, ge=0, le=10)
    upload_timeout_seconds: float = Field(default=30.0, gt=0, le=120)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> Self:
        total = round(
            self.confidence_weight_field_decisiveness
            + self.confidence_weight_watertightness
            + self.confidence_weight_volume_plausibility,
            _WEIGHT_PRECISION,
        )
        if total != 1.0:
            raise ValueError(
                f"confidence weights must sum to 1.0 at {_WEIGHT_PRECISION}dp, got {total}"
            )
        return self

    @model_validator(mode="after")
    def _bands_are_ordered(self) -> Self:
        if self.confidence_band_low_max > self.confidence_band_high_min:
            raise ValueError("confidence_band_low_max must not exceed confidence_band_high_min")
        return self

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
            "services/reconstruction: invalid environment. Refusing to start.\n"
            + "\n".join(lines)
            + "\nSee .env.example for the full set.\n"
        )
        raise SystemExit(1) from exc
