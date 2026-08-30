from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import cloudevent, storage_object

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "contracts"
    / "schemas"
    / "agent-job.schema.json"
)


def test_a_processed_job_is_readable_afterwards(client: TestClient) -> None:
    """Definition-of-Done item 4: the decision chain has to survive the request
    that produced it."""
    ack = client.post(
        "/v1/events/scan",
        content=cloudevent(storage_object())[1],
        headers=cloudevent(storage_object())[0],
    ).json()
    response = client.get(f"/v1/jobs/{ack['jobId']}")
    assert response.status_code == 200
    assert response.json()["jobId"] == ack["jobId"]


def test_the_response_carries_only_contract_properties(client: TestClient) -> None:
    headers, body = cloudevent(storage_object())
    ack = client.post("/v1/events/scan", content=body, headers=headers).json()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    allowed = set(schema["properties"].keys())
    assert set(client.get(f"/v1/jobs/{ack['jobId']}").json().keys()) <= allowed


def test_the_decision_trail_reads_top_to_bottom(client: TestClient) -> None:
    headers, body = cloudevent(storage_object())
    ack = client.post("/v1/events/scan", content=body, headers=headers).json()
    decisions = client.get(f"/v1/jobs/{ack['jobId']}").json()["decisions"]
    assert [entry["state"] for entry in decisions] == [
        "queued",
        "triaged",
        "simulating",
        "reporting",
    ]
    assert [entry["actor"] for entry in decisions] == ["ingest", "triage", "gate", "gate"]


def test_an_unknown_job_is_a_404_with_the_standard_envelope(client: TestClient) -> None:
    response = client.get("/v1/jobs/scan-000000000000000")
    assert response.status_code == 404
    assert response.json() == {
        "error": "no job with that id",
        "requestId": response.headers["x-request-id"],
    }


@pytest.mark.parametrize("job_id", ["..", "scan", "SCAN-9F2C41AB77D05E13", "scan_9f2c41ab77d05e13"])
def test_a_job_id_that_could_escape_the_collection_never_reaches_the_store(
    client: TestClient, job_id: str
) -> None:
    """The router refuses it against the contract's own pattern, so a Firestore
    document path is never assembled from a caller's string."""
    assert client.get(f"/v1/jobs/{job_id}").status_code in (404, 422)
