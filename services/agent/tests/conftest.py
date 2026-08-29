from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rinne_agent.app import create_app
from rinne_agent.config import Settings

#: A 1x1 PNG. Real magic bytes, so the layer-4 check passes without a fixture file.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

SCAN_BUCKET = "rinne-scans-rinnehackathon"
SCAN_PREFIX = "scan-queue/"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        service_version="test-1",
        gcp_project_id="rinnehackathon",
        gcp_region="asia-southeast1",
        k_revision="rinne-agent-00001-abc",
        enable_docs=False,
        store_mode="memory",
        object_mode="memory",
        triage_mode="stub",
        scan_bucket=SCAN_BUCKET,
        scan_prefix=SCAN_PREFIX,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def storage_object(
    *,
    bucket: str = SCAN_BUCKET,
    name: str = "scan-queue/desk.jpg",
    generation: str = "1756400000000000",
    content_type: str = "image/png",
    size: int = len(PNG_BYTES),
) -> dict[str, Any]:
    """The GCS object resource, exactly as a storage event carries it."""
    return {
        "kind": "storage#object",
        "bucket": bucket,
        "name": name,
        "generation": generation,
        "contentType": content_type,
        "size": str(size),
    }


def cloudevent(document: dict[str, Any], *, event_id: str = "ce-1") -> tuple[dict[str, str], bytes]:
    """Binary-mode CloudEvent, the shape Eventarc delivers to Cloud Run."""
    headers = {
        "ce-id": event_id,
        "ce-source": "//storage.googleapis.com/projects/_/buckets/rinne-scans-rinnehackathon",
        "ce-specversion": "1.0",
        "ce-type": "google.cloud.storage.object.v1.finalized",
        "ce-subject": f"objects/{document['name']}",
        "content-type": "application/json",
    }
    return headers, json.dumps(document).encode()


def pubsub_push(
    document: dict[str, Any], *, message_id: str = "ps-1", event_type: str = "OBJECT_FINALIZE"
) -> tuple[dict[str, str], bytes]:
    """Plain Pub/Sub push, the shape a curl or `gcloud pubsub publish` produces."""
    envelope = {
        "message": {
            "data": base64.b64encode(json.dumps(document).encode()).decode(),
            "attributes": {"eventType": event_type, "bucketId": document["bucket"]},
            "messageId": message_id,
        },
        "subscription": "projects/rinnehackathon/subscriptions/rinne-scan-queue",
    }
    return {"content-type": "application/json"}, json.dumps(envelope).encode()
