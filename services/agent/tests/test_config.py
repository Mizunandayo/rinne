from __future__ import annotations

import pytest
from pydantic import ValidationError

from rinne_agent.config import Settings


def test_defaults_are_safe() -> None:
    settings = Settings()
    assert settings.app_env == "development"
    assert settings.enable_docs is False
    assert settings.max_request_bytes == 1_048_576


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
