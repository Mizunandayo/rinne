from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rinne_agent.contracts import AgentJob
from rinne_agent.contracts.agent_job import JobActor, JobState
from rinne_agent.gcp.firestore import (
    MemoryJobStore,
    PreconditionFailedError,
    decode_fields,
    decode_value,
    encode_fields,
    encode_value,
    from_document,
    to_document,
)

STAMP = datetime(2026, 8, 29, 4, 20, tzinfo=UTC)


def job(state: JobState = JobState.queued) -> AgentJob:
    return AgentJob.model_validate(
        {
            "schemaVersion": 1,
            "jobId": "scan-9f2c41ab77d05e13",
            "state": state,
            "attempts": 1,
            "createdAt": STAMP,
            "updatedAt": STAMP,
            "source": {
                "bucket": "rinne-scans-rinnehackathon",
                "object": "scan-queue/desk.jpg",
                "generation": "1756400000000000",
                "contentType": "image/png",
                "sizeBytes": 128,
                "receivedAt": STAMP,
            },
            "decisions": [
                {
                    "at": STAMP,
                    "state": JobState.queued,
                    "actor": JobActor.ingest,
                    "summary": "Storage event accepted; job created.",
                }
            ],
        }
    )


class TestValueCodec:
    def test_integers_are_encoded_as_strings(self) -> None:
        """Firestore's integerValue is int64 and is JSON-encoded as a string in
        both directions. This is where a hand-written codec usually goes wrong."""
        assert encode_value(128) == {"integerValue": "128"}
        assert decode_value({"integerValue": "128"}) == 128

    def test_booleans_are_not_treated_as_integers(self) -> None:
        """bool is a subclass of int in Python, so the order of the checks in
        encode_value is load-bearing rather than stylistic."""
        assert encode_value(True) == {"booleanValue": True}

    def test_null_is_the_literal_enum_value(self) -> None:
        assert encode_value(None) == {"nullValue": "NULL_VALUE"}
        assert decode_value({"nullValue": "NULL_VALUE"}) is None

    def test_floats_stay_doubles(self) -> None:
        assert encode_value(0.95) == {"doubleValue": 0.95}
        assert decode_value({"doubleValue": 0.95}) == pytest.approx(0.95)

    def test_an_empty_array_decodes_without_a_values_key(self) -> None:
        """Firestore omits `values` entirely for an empty array."""
        assert decode_value({"arrayValue": {}}) == []

    def test_an_empty_map_decodes_without_a_fields_key(self) -> None:
        assert decode_value({"mapValue": {}}) == {}

    def test_nested_structures_round_trip(self) -> None:
        original = {"a": [1, {"b": True, "c": None}], "d": "x"}
        assert decode_fields(encode_fields(original)) == original

    def test_an_unsupported_type_is_a_loud_failure(self) -> None:
        with pytest.raises(TypeError):
            encode_value({1, 2, 3})


class TestDocumentRoundTrip:
    def test_a_job_survives_a_full_round_trip(self) -> None:
        document = to_document(job())
        assert from_document(document) == job()

    def test_absent_optionals_are_genuinely_absent(self) -> None:
        """exclude_none, not null placeholders: a queued job has no error and no
        triage, and the stored document must say so by omission."""
        fields = to_document(job())["fields"]
        assert "error" not in fields
        assert "triage" not in fields
        assert "lastGoodState" not in fields

    def test_a_document_that_no_longer_validates_is_a_named_rule(self) -> None:
        from rinne_agent.errors import RuleError

        broken = {"fields": encode_fields({"schemaVersion": 1, "jobId": "nope"})}
        with pytest.raises(RuleError) as caught:
            from_document(broken)
        assert caught.value.status == 500


class TestMemoryStore:
    async def test_create_then_get(self) -> None:
        store = MemoryJobStore()
        created = await store.create(job())
        found = await store.get("scan-9f2c41ab77d05e13")
        assert found is not None
        assert found.update_time == created.update_time
        assert found.job.state is JobState.queued

    async def test_get_returns_none_for_an_unknown_id(self) -> None:
        assert await MemoryJobStore().get("scan-000000000000000") is None

    async def test_create_is_create_only(self) -> None:
        """The same semantics as ifGenerationMatch=0 on the mesh upload: a
        second delivery of one event is refused, not silently duplicated."""
        store = MemoryJobStore()
        await store.create(job())
        with pytest.raises(PreconditionFailedError):
            await store.create(job())

    async def test_save_is_a_compare_and_swap(self) -> None:
        store = MemoryJobStore()
        created = await store.create(job())
        await store.save(job(JobState.triaged), expected=created.update_time)
        # The version the first writer held is now stale, which is exactly what
        # a second Cloud Run instance holding a redelivered message would have.
        with pytest.raises(PreconditionFailedError):
            await store.save(job(JobState.skipped_low_risk), expected=created.update_time)

    async def test_save_refuses_a_document_that_does_not_exist(self) -> None:
        with pytest.raises(PreconditionFailedError):
            await MemoryJobStore().save(job(), expected="whatever")
