from __future__ import annotations

import base64
import json

import pytest

from conftest import SCAN_BUCKET, SCAN_PREFIX, cloudevent, pubsub_push, storage_object
from rinne_agent.errors import RuleError
from rinne_agent.ingest import Ignored, ScanEvent, derive_job_id, parse_delivery

MAX_BYTES = 6_291_456


def parse(headers: dict[str, str], body: bytes):
    return parse_delivery(
        headers=headers,
        body=body,
        bucket=SCAN_BUCKET,
        prefix=SCAN_PREFIX,
        max_bytes=MAX_BYTES,
    )


def test_a_binary_cloudevent_from_eventarc_parses() -> None:
    parsed = parse(*cloudevent(storage_object()))
    assert isinstance(parsed, ScanEvent)
    assert parsed.object_name == "scan-queue/desk.jpg"
    assert parsed.generation == "1756400000000000"
    assert parsed.event_id == "ce-1"


def test_a_pubsub_push_envelope_parses_to_the_same_event() -> None:
    from_eventarc = parse(*cloudevent(storage_object()))
    from_pubsub = parse(*pubsub_push(storage_object()))
    assert isinstance(from_eventarc, ScanEvent)
    assert isinstance(from_pubsub, ScanEvent)
    assert from_eventarc.job_id == from_pubsub.job_id


def test_the_job_id_is_deterministic_and_contract_shaped() -> None:
    first = derive_job_id(SCAN_BUCKET, "scan-queue/desk.jpg", "1")
    again = derive_job_id(SCAN_BUCKET, "scan-queue/desk.jpg", "1")
    assert first == again
    assert first.startswith("scan-")
    assert len(first) == 21


def test_a_new_generation_is_a_new_job() -> None:
    """Re-uploading an object is a new scan; redelivering one upload is not."""
    assert derive_job_id(SCAN_BUCKET, "scan-queue/desk.jpg", "1") != derive_job_id(
        SCAN_BUCKET, "scan-queue/desk.jpg", "2"
    )


def test_an_event_naming_another_bucket_is_ignored() -> None:
    parsed = parse(*cloudevent(storage_object(bucket="some-other-bucket")))
    assert isinstance(parsed, Ignored)
    # The refusal must not echo the bucket that was named. It is payload.
    assert "some-other-bucket" not in parsed.rule


def test_an_object_outside_the_prefix_is_ignored() -> None:
    parsed = parse(*cloudevent(storage_object(name="meshes/scan-1.glb")))
    assert isinstance(parsed, Ignored)


def test_a_folder_placeholder_is_ignored() -> None:
    parsed = parse(*cloudevent(storage_object(name="scan-queue/")))
    assert isinstance(parsed, Ignored)


def test_a_non_image_content_type_is_ignored() -> None:
    parsed = parse(*cloudevent(storage_object(content_type="text/plain")))
    assert isinstance(parsed, Ignored)


def test_an_empty_object_is_ignored() -> None:
    parsed = parse(*cloudevent(storage_object(size=0)))
    assert isinstance(parsed, Ignored)


def test_an_oversized_object_is_ignored() -> None:
    parsed = parse(*cloudevent(storage_object(size=MAX_BYTES + 1)))
    assert isinstance(parsed, Ignored)


def test_a_malformed_generation_is_ignored() -> None:
    parsed = parse(*cloudevent(storage_object(generation="latest")))
    assert isinstance(parsed, Ignored)


def test_a_delete_event_is_ignored() -> None:
    headers, body = cloudevent(storage_object())
    headers["ce-type"] = "google.cloud.storage.object.v1.deleted"
    assert isinstance(parse(headers, body), Ignored)


def test_a_request_that_is_not_a_delivery_at_all_is_an_http_error() -> None:
    """The only case that is NOT acknowledged. Eventarc cannot produce it."""
    with pytest.raises(RuleError) as caught:
        parse({"content-type": "application/json"}, json.dumps({"hello": "world"}).encode())
    assert caught.value.status == 400
    assert caught.value.retryable is False


def test_an_unparseable_body_is_an_http_error() -> None:
    with pytest.raises(RuleError):
        parse({"ce-type": "google.cloud.storage.object.v1.finalized"}, b"not json")


def test_pubsub_data_that_is_not_base64_is_an_http_error() -> None:
    envelope = {"message": {"data": "!!!not base64!!!", "messageId": "1"}}
    with pytest.raises(RuleError):
        parse({"content-type": "application/json"}, json.dumps(envelope).encode())


def test_pubsub_data_that_is_base64_of_junk_is_an_http_error() -> None:
    envelope = {"message": {"data": base64.b64encode(b"not json").decode(), "messageId": "1"}}
    with pytest.raises(RuleError):
        parse({"content-type": "application/json"}, json.dumps(envelope).encode())
