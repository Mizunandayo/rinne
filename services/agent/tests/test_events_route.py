from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import cloudevent, pubsub_push, storage_object
from rinne_agent.agents.runtime import StubSelector, StubTriager, TriageOutcome
from rinne_agent.agents.triage import TriageOutput
from rinne_agent.clients.physics import StubSimulator
from rinne_agent.clients.reconstruction import StubReconstructor
from rinne_agent.contracts.agent_job import JobState
from rinne_agent.decide import Decider
from rinne_agent.errors import RuleError
from rinne_agent.pipeline import Pipeline

EVENTS = "/v1/events/scan"


def post(client: TestClient, headers: dict[str, str], body: bytes):
    return client.post(EVENTS, content=body, headers=headers)


class FailingReader:
    """A reader that always refuses, with a configurable retryability."""

    def __init__(self, *, retryable: bool) -> None:
        self._retryable = retryable

    async def read(self, *, bucket: str, object_name: str, generation: str) -> bytes:
        del bucket, object_name, generation
        raise RuleError("the scan object could not be read", retryable=self._retryable)


def swap(app: FastAPI, **changes: object) -> None:
    """Replace one collaborator on the live pipeline, keeping the rest."""
    current: Pipeline = app.state.pipeline
    app.state.pipeline = Pipeline(
        store=changes.get("store", current.store),  # type: ignore[arg-type]
        reader=changes.get("reader", current.reader),  # type: ignore[arg-type]
        triager=changes.get("triager", current.triager),  # type: ignore[arg-type]
        decider=changes.get("decider", current.decider),  # type: ignore[arg-type]
        max_attempts=changes.get("max_attempts", current.max_attempts),  # type: ignore[arg-type]
    )


def redecide(app: FastAPI, **changes: object) -> None:
    """The same, one level down, for the collaborators of the decision half."""
    now: Decider = app.state.pipeline.decider
    swap(
        app,
        decider=Decider(
            selector=changes.get("selector", now.selector),  # type: ignore[arg-type]
            reconstructor=changes.get("reconstructor", now.reconstructor),  # type: ignore[arg-type]
            simulator=changes.get("simulator", now.simulator),  # type: ignore[arg-type]
            thresholds=changes.get("thresholds", now.thresholds),  # type: ignore[arg-type]
            solver=changes.get("solver", now.solver),  # type: ignore[arg-type]
        ),
    )


def test_a_cloudevent_runs_the_whole_loop_to_reporting(client: TestClient) -> None:
    response = post(client, *cloudevent(storage_object()))
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "processed"
    assert body["state"] == JobState.reporting.value
    assert body["jobId"].startswith("scan-")


def test_a_pubsub_push_produces_the_same_job(client: TestClient) -> None:
    from_ce = post(client, *cloudevent(storage_object())).json()
    from_ps = post(client, *pubsub_push(storage_object())).json()
    # Same object, same generation, same job. The second is a duplicate.
    assert from_ps["jobId"] == from_ce["jobId"]
    assert from_ps["outcome"] == "duplicate"


def test_a_redelivery_is_acknowledged_and_does_no_work(client: TestClient) -> None:
    first = post(client, *cloudevent(storage_object()))
    second = post(client, *cloudevent(storage_object()))
    assert first.json()["outcome"] == "processed"
    assert second.status_code == 200
    assert second.json()["outcome"] == "duplicate"


def test_a_low_risk_object_terminates_in_skipped_low_risk(app: FastAPI, client: TestClient) -> None:
    """The most common outcome, and a legitimate one. Nothing downstream runs."""
    swap(app, triager=StubTriager(review=False, shape="flat-wide"))
    body = post(client, *cloudevent(storage_object())).json()
    assert body["state"] == JobState.skipped_low_risk.value

    job = client.get(f"/v1/jobs/{body['jobId']}").json()
    assert job["state"] == "skipped_low_risk"
    assert job["triage"]["review"] is False
    assert "selection" not in job


def test_a_reviewed_job_carries_every_record_the_loop_produced(client: TestClient) -> None:
    body = post(client, *cloudevent(storage_object())).json()
    job = client.get(f"/v1/jobs/{body['jobId']}").json()
    assert job["selection"]["kind"] == "tip"
    assert job["reconstruction"]["meshUri"].startswith("gs://")
    assert job["simulation"]["verdict"] == "stable"
    assert job["gate"]["decision"] == "report"
    assert job["gate"]["policy"] == "min-confidence-v1"


def test_low_confidence_escalates_to_awaiting_verification(
    app: FastAPI, client: TestClient
) -> None:
    """Section 7 step 3. The gate is the only thing that decides this."""
    redecide(app, reconstructor=StubReconstructor(confidence=0.22))
    body = post(client, *cloudevent(storage_object())).json()
    assert body["state"] == JobState.awaiting_verification.value

    job = client.get(f"/v1/jobs/{body['jobId']}").json()
    assert job["gate"]["decision"] == "escalate"
    assert job["gate"]["reasons"] == ["low-reconstruction-confidence"]
    assert job["decisions"][-1]["actor"] == "gate"


def test_an_unsupported_physics_test_escalates_rather_than_reporting_stable(
    app: FastAPI, client: TestClient
) -> None:
    """A load test settles untouched and returns stable. Reporting that would be a lie."""
    redecide(app, simulator=StubSimulator(notices=["load-test-not-implemented"]))
    body = post(client, *cloudevent(storage_object())).json()
    assert body["state"] == JobState.awaiting_verification.value

    job = client.get(f"/v1/jobs/{body['jobId']}").json()
    assert job["gate"]["reasons"] == ["physics-test-unsupported"]


def test_a_selection_of_none_fails_the_job_from_triaged(app: FastAPI, client: TestClient) -> None:
    redecide(app, selector=StubSelector(kind="none"))
    body = post(client, *cloudevent(storage_object())).json()
    assert body["outcome"] == "failed"

    job = client.get(f"/v1/jobs/{body['jobId']}").json()
    assert job["state"] == "failed"
    assert job["lastGoodState"] == "triaged"
    assert job["error"]["actor"] == "gate"


def test_an_object_in_another_bucket_is_acknowledged_not_retried(client: TestClient) -> None:
    response = post(client, *cloudevent(storage_object(bucket="rinne-artifacts-rinnehackathon")))
    assert response.status_code == 200
    assert response.json()["outcome"] == "ignored"


def test_a_mesh_upload_does_not_start_a_job(client: TestClient) -> None:
    """The scan bucket is separate from the artifacts bucket precisely so this
    cannot happen, and the prefix check is the second line of the same defence."""
    response = post(client, *cloudevent(storage_object(name="meshes/scan-1.glb")))
    assert response.json()["outcome"] == "ignored"


def test_a_malformed_delivery_is_a_400_and_not_a_poison_message(client: TestClient) -> None:
    response = client.post(EVENTS, json={"hello": "world"})
    assert response.status_code == 400
    assert response.json()["error"]
    assert response.json()["requestId"]


def test_a_permanent_failure_is_recorded_and_acknowledged(app: FastAPI, client: TestClient) -> None:
    swap(app, reader=FailingReader(retryable=False))
    response = post(client, *cloudevent(storage_object()))
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "failed"
    assert body["state"] == JobState.failed.value

    job = client.get(f"/v1/jobs/{body['jobId']}").json()
    assert job["state"] == "failed"
    assert job["lastGoodState"] == "queued"
    assert job["error"]["retryable"] is False


def test_a_retryable_failure_returns_503_so_pubsub_delivers_again(
    app: FastAPI, client: TestClient
) -> None:
    swap(app, reader=FailingReader(retryable=True))
    response = post(client, *cloudevent(storage_object()))
    assert response.status_code == 503
    assert response.json()["outcome"] == "retry"


def test_bytes_that_do_not_match_the_declared_type_are_refused(
    app: FastAPI, client: TestClient
) -> None:
    reader = app.state.pipeline.reader
    document = storage_object(name="scan-queue/liar.png")
    reader.put(
        bucket=document["bucket"],
        object_name=document["name"],
        generation=document["generation"],
        data=b"GIF89a not a png at all",
    )
    body = post(client, *cloudevent(document)).json()
    assert body["outcome"] == "failed"

    job = client.get(f"/v1/jobs/{body['jobId']}").json()
    assert job["error"]["rule"] == "scan bytes do not match the declared image type"


class ExplodingTriager(StubTriager):
    async def triage(self, *, job_id: str, image: bytes, mime_type: str) -> TriageOutcome:
        del job_id, image, mime_type
        raise RuleError("the triage model returned an unusable answer", retryable=False)


def test_a_bad_model_answer_fails_the_job_rather_than_the_request(
    app: FastAPI, client: TestClient
) -> None:
    swap(app, triager=ExplodingTriager())
    body = post(client, *cloudevent(storage_object())).json()
    assert body["outcome"] == "failed"

    job = client.get(f"/v1/jobs/{body['jobId']}").json()
    assert job["error"]["rule"] == "the triage model returned an unusable answer"
    assert job["lastGoodState"] == "queued"


@pytest.mark.parametrize("shape", ["tall-narrow", "stack", "irregular"])
def test_the_recorded_triage_carries_the_model_and_the_shape(
    app: FastAPI, client: TestClient, shape: str
) -> None:
    swap(app, triager=StubTriager(review=True, shape=shape))
    body = post(client, *cloudevent(storage_object())).json()
    job = client.get(f"/v1/jobs/{body['jobId']}").json()
    assert job["triage"]["shape"] == shape
    assert job["triage"]["model"] == "stub-triage"
    assert job["triage"]["basis"] == "flash-triage-v1"
    assert [entry["actor"] for entry in job["decisions"]][1] == "triage"


def test_the_output_schema_of_the_stub_matches_the_model_contract() -> None:
    assert set(TriageOutput.model_fields) == {"review", "shape", "confidence", "rationale"}
