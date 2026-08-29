from __future__ import annotations

import pytest
from pydantic import ValidationError

from rinne_agent.config import Settings


def test_defaults_are_safe() -> None:
    settings = Settings()
    assert settings.app_env == "development"
    assert settings.enable_docs is False
    assert settings.max_request_bytes == 1_048_576


def test_production_defaults_call_the_real_things() -> None:
    """The test doubles are opt-in. A deploy that forgot to set them still gets
    Firestore, GCS and Flash rather than a canned answer."""
    settings = Settings()
    assert settings.store_mode == "firestore"
    assert settings.object_mode == "gcs"
    assert settings.triage_mode == "flash"


def test_the_scan_queue_is_a_separate_bucket_from_the_artifacts_bucket() -> None:
    """A trigger on the artifacts bucket would fire on the meshes the system
    itself writes."""
    settings = Settings()
    assert settings.scan_bucket == "rinne-scans-rinnehackathon"
    assert settings.scan_prefix == "scan-queue/"


def test_thinking_is_off_by_default_on_the_triage_model() -> None:
    settings = Settings()
    assert settings.triage_model == "gemini-3.5-flash"
    assert settings.triage_thinking_budget == 0


def test_docs_can_never_be_enabled_in_production() -> None:
    """enable_docs=True must not be sufficient. Turning docs on in production
    requires a code change, not an environment variable."""
    settings = Settings(app_env="production", enable_docs=True)
    assert settings.docs_enabled is False


def test_invalid_port_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(port=70_000)


def test_invalid_environment_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="staging")


def test_settings_are_frozen() -> None:
    settings = Settings()
    with pytest.raises(ValidationError):
        settings.port = 9999  # type: ignore[misc]


def test_the_attempt_cap_cannot_exceed_the_section_12_ceiling() -> None:
    with pytest.raises(ValidationError):
        Settings(max_attempts=7)


def test_a_traversing_scan_prefix_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(scan_prefix="../")


def test_cloud_run_is_detected_from_k_service_alone() -> None:
    assert Settings().is_cloud_run is False
    assert Settings(k_service="rinne-agent").is_cloud_run is True
