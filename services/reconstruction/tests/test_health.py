from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "contracts"
    / "schemas"
    / "health.schema.json"
)


def test_livez_returns_a_contract_valid_report(client: TestClient) -> None:
    response = client.get("/livez")
    assert response.status_code == 200

    body = response.json()
    assert body["service"] == "reconstruction"
    assert body["status"] == "ok"
    assert body["version"] == "test-1"
    assert body["revision"] == "rinne-reconstruction-00001-abc"


def test_livez_emits_only_contract_properties(client: TestClient) -> None:
    """The response model is generated from the schema, so a field that is not
    in the contract cannot reach a caller. This asserts that, rather than
    trusting it."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    allowed = set(schema["properties"].keys())
    assert set(client.get("/livez").json().keys()) <= allowed


def test_readyz_reports_the_pipeline_and_the_store(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    named = {dep["name"]: dep for dep in body["dependencies"]}
    assert named["pipeline"]["status"] == "ok"
    assert named["pipeline"]["detail"].startswith("stub ")
    # device is part of the readiness detail on purpose: on Day 3 this string
    # is how you see at a glance whether the GPU is actually in the path.
    assert named["pipeline"]["detail"].endswith(" on cpu")
    assert named["storage"]["status"] == "ok"
    assert named["storage"]["detail"] == "memory"


def test_readyz_reports_the_inflight_gauge(client: TestClient) -> None:
    # Probes are exempt from the gauge, so a quiet service reports zero rather
    # than reporting the prober.
    assert client.get("/readyz").json()["detail"] == "0 in flight, peak 0"


def test_security_headers_are_present(client: TestClient) -> None:
    headers = client.get("/livez").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in headers["content-security-policy"]
    assert headers["cache-control"] == "no-store"


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/livez", headers={"x-request-id": "probe-123"})
    assert response.headers["x-request-id"] == "probe-123"


def test_request_id_is_generated_when_absent(client: TestClient) -> None:
    assert client.get("/livez").headers["x-request-id"]


def test_openapi_is_not_served_when_docs_are_disabled(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404


def test_oversized_declared_body_is_rejected_before_a_handler_runs(client: TestClient) -> None:
    # Layer 1: the DECLARED length, refused before a byte is read.
    response = client.post(
        "/v1/reconstruct",
        content=b"x" * 10,
        headers={"content-length": "99999999"},
    )
    assert response.status_code == 413


@pytest.mark.parametrize("path", ["/", "/admin", "/healthz"])
def test_unknown_routes_return_404_without_detail(client: TestClient, path: str) -> None:
    # /healthz is in this list deliberately.
    response = client.get(path)
    assert response.status_code == 404
    assert "Traceback" not in response.text
