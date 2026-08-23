from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rinne_agent.app import create_app
from rinne_agent.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        service_version="test-1",
        gcp_project_id="rinnehackathon",
        gcp_region="asia-southeast1",
        k_revision="rinne-agent-00001-abc",
        enable_docs=False,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
