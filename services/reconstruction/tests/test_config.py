from __future__ import annotations

import pytest
from pydantic import ValidationError

from rinne_reconstruction.config import Settings


def test_defaults_match_the_spec_appendix() -> None:
    settings = Settings()
    assert settings.app_env == "development"
    assert settings.enable_docs is False
    assert settings.max_request_bytes == 26_214_400
    assert settings.max_metadata_chars == 4096
    assert settings.max_images == 4
    assert settings.max_image_bytes == 6_291_456
    assert settings.max_image_pixels == 40_000_000
    assert settings.max_image_edge == 1536
    assert settings.pipeline_name == "stub"
    assert settings.storage_mode == "gcs"
    assert settings.gcs_bucket == "rinne-artifacts-rinnehackathon"


def test_the_day_two_weights_sum_to_one() -> None:
    """The renormalised three-component weights, at 4dp.

    volume_plausibility is 0.1177 rather than 0.1176 because the residual has
    to go somewhere; the naive value sums to 0.9999 and the validator below
    rejects it. This test is what makes that a rule instead of a comment.
    """
    settings = Settings()
    total = (
        settings.confidence_weight_field_decisiveness
        + settings.confidence_weight_watertightness
        + settings.confidence_weight_volume_plausibility
    )
    assert round(total, 4) == 1.0


def test_weights_that_do_not_sum_to_one_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(confidence_weight_volume_plausibility=0.1176)


def test_bands_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        Settings(confidence_band_low_max=0.9, confidence_band_high_min=0.2)


def test_confidence_ships_uncalibrated_until_day_three() -> None:
    assert Settings().confidence_calibrated is False


def test_docs_can_never_be_enabled_in_production() -> None:
    """enable_docs=True must not be sufficient. Turning docs on in production
    requires a code change, not an environment variable."""
    settings = Settings(app_env="production", enable_docs=True)
    assert settings.docs_enabled is False


def test_invalid_port_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(port=70_000)


def test_request_body_cap_stays_under_the_cloud_run_ceiling() -> None:
    # Cloud Run refuses a request body over 32 MiB at the edge. A cap above
    # that would be a limit this service could never actually enforce.
    assert Settings().max_request_bytes < 33_554_432
    with pytest.raises(ValidationError):
        Settings(max_request_bytes=40_000_000)


def test_settings_are_frozen() -> None:
    settings = Settings()
    with pytest.raises(ValidationError):
        settings.port = 9999  # type: ignore[misc]
