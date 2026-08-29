"""The job store: one AgentJob per Firestore document, over the REST API"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Final, Protocol
from urllib.parse import quote

import httpx2
from pydantic import ValidationError

from rinne_agent.contracts import AgentJob
from rinne_agent.errors import RuleError
from rinne_agent.gcp.tokens import DATASTORE_SCOPE, TokenError, TokenSource

logger = logging.getLogger(__name__)

_FIRESTORE_ROOT: Final = "https://firestore.googleapis.com/v1"

QueryParams = list[tuple[str, str | int | float | bool | None]]

_FIELD_PATHS: Final[tuple[str, ...]] = (
    "schemaVersion",
    "jobId",
    "state",
    "lastGoodState",
    "attempts",
    "createdAt",
    "updatedAt",
    "source",
    "triage",
    "error",
    "decisions",
)

_PRECONDITION_STATUSES: Final[frozenset[str]] = frozenset(
    {"ALREADY_EXISTS", "FAILED_PRECONDITION", "NOT_FOUND"}
)


@dataclass(frozen=True)
class StoredJob:
    """A job plus the exact version it was read at"""

    job: AgentJob
    update_time: str


class PreconditionFailedError(RuntimeError):
    """The document was not in the state the write required. Never an error."""


def encode_value(value: object) -> dict[str, Any]:
    """Python value to a Firestore Value. bool is checked before int on purpose."""
    if value is None:
        return {"nullValue": "NULL_VALUE"}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [encode_value(item) for item in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": encode_fields(value)}}
    raise TypeError(f"unsupported Firestore value type: {type(value).__name__}")


def encode_fields(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {key: encode_value(value) for key, value in document.items()}


def decode_value(value: dict[str, Any]) -> Any:
    if "nullValue" in value:
        return None
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "stringValue" in value:
        return str(value["stringValue"])
    if "timestampValue" in value:
        return str(value["timestampValue"])
    if "arrayValue" in value:
        items = value["arrayValue"].get("values", [])
        return [decode_value(item) for item in items]
    if "mapValue" in value:
        return decode_fields(value["mapValue"].get("fields", {}))
    raise TypeError(f"unsupported Firestore value: {sorted(value)}")


def decode_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: decode_value(value) for key, value in fields.items()}


def to_document(job: AgentJob) -> dict[str, Any]:
    """Contract-shaped JSON, camelCase, with absent optionals genuinely absent."""
    payload: dict[str, Any] = job.model_dump(mode="json", by_alias=True, exclude_none=True)
    return {"fields": encode_fields(payload)}


def from_document(document: dict[str, Any]) -> AgentJob:
    try:
        return AgentJob.model_validate(decode_fields(document.get("fields", {})))
    except (ValidationError, TypeError) as exc:
        logger.error("stored job failed contract validation")
        raise RuleError(
            "the stored job is not contract-valid", status=500, retryable=False
        ) from exc


class JobStore(Protocol):
    """Create-only writes and compare-and-swap updates. Nothing else."""

    @property
    def mode(self) -> str: ...

    async def create(self, job: AgentJob) -> StoredJob: ...

    async def get(self, job_id: str) -> StoredJob | None: ...

    async def save(self, job: AgentJob, *, expected: str) -> StoredJob: ...


class MemoryJobStore:
    """The test path, with the SAME preconditions as Firestore.

    The version counter is what makes it a real double: a test can lose a
    compare-and-swap here exactly the way a second Cloud Run instance does.
    """

    def __init__(self) -> None:
        self._documents: dict[str, tuple[AgentJob, int]] = {}

    @property
    def mode(self) -> str:
        return "memory"

    @staticmethod
    def _stamp(version: int) -> str:
        return f"2026-08-29T00:00:{version:02d}.000000Z"

    async def create(self, job: AgentJob) -> StoredJob:
        if job.job_id in self._documents:
            raise PreconditionFailedError(job.job_id)
        self._documents[job.job_id] = (job, 1)
        return StoredJob(job=job, update_time=self._stamp(1))

    async def get(self, job_id: str) -> StoredJob | None:
        found = self._documents.get(job_id)
        if found is None:
            return None
        job, version = found
        return StoredJob(job=job, update_time=self._stamp(version))

    async def save(self, job: AgentJob, *, expected: str) -> StoredJob:
        found = self._documents.get(job.job_id)
        if found is None:
            raise PreconditionFailedError(job.job_id)
        _, version = found
        if self._stamp(version) != expected:
            raise PreconditionFailedError(job.job_id)
        self._documents[job.job_id] = (job, version + 1)
        return StoredJob(job=job, update_time=self._stamp(version + 1))


class FirestoreJobStore:
    """One collection, three operations, bounded retry."""

    def __init__(
        self,
        *,
        tokens: TokenSource,
        project_id: str,
        database: str,
        collection: str,
        timeout_seconds: float,
        max_attempts: int,
        backoff_seconds: float,
    ) -> None:
        self._tokens = tokens
        self._collection_url = (
            f"{_FIRESTORE_ROOT}/projects/{project_id}"
            f"/databases/{quote(database, safe='()')}/documents/{quote(collection, safe='')}"
        )
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds

    @property
    def mode(self) -> str:
        return "firestore"

    def _document_url(self, job_id: str) -> str:
        return f"{self._collection_url}/{quote(job_id, safe='')}"

    @staticmethod
    def _status_of(response: httpx2.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return ""
        error = body.get("error") if isinstance(body, dict) else None
        return str(error.get("status", "")) if isinstance(error, dict) else ""

    async def _request(
        self,
        *,
        method: str,
        url: str,
        params: QueryParams,
        json_body: dict[str, Any] | None,
    ) -> httpx2.Response:
        async with httpx2.AsyncClient(timeout=self._timeout_seconds) as client:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    token = await self._tokens.token(client, DATASTORE_SCOPE)
                except TokenError as exc:
                    raise RuleError(
                        "job store credentials are unavailable", retryable=True
                    ) from exc

                try:
                    response = await client.request(
                        method,
                        url,
                        params=params,
                        json=json_body,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                except httpx2.HTTPError as exc:
                    if attempt >= self._max_attempts:
                        raise RuleError("the job store is unreachable", retryable=True) from exc
                    await asyncio.sleep(self._backoff_seconds * attempt)
                    continue

                if response.status_code == 401:
                    self._tokens.invalidate(DATASTORE_SCOPE)
                    if attempt >= self._max_attempts:
                        raise RuleError("job store credentials were rejected", retryable=True)
                    await asyncio.sleep(self._backoff_seconds * attempt)
                    continue

                if response.status_code < 500:
                    return response

                logger.warning(
                    "job store call failed",
                    extra={"status": response.status_code, "attempt": attempt},
                )
                if attempt >= self._max_attempts:
                    return response
                await asyncio.sleep(self._backoff_seconds * attempt)

        raise RuleError("the job store is unreachable", retryable=True)  # pragma: no cover

    def _read_response(self, response: httpx2.Response) -> StoredJob:
        if response.status_code != 200:
            if self._status_of(response) in _PRECONDITION_STATUSES or response.status_code in (
                404,
                409,
            ):
                raise PreconditionFailedError(response.request.url.path)
            logger.error("job store write refused", extra={"status": response.status_code})
            raise RuleError(
                "the job store refused the write",
                retryable=response.status_code >= 500,
            )
        document = response.json()
        if not isinstance(document, dict):
            raise RuleError("the job store returned an unusable document", retryable=False)
        return StoredJob(
            job=from_document(document), update_time=str(document.get("updateTime", ""))
        )

    async def create(self, job: AgentJob) -> StoredJob:
        params: QueryParams = [("currentDocument.exists", "false")]
        params += [("updateMask.fieldPaths", path) for path in _FIELD_PATHS]
        response = await self._request(
            method="PATCH",
            url=self._document_url(job.job_id),
            params=params,
            json_body=to_document(job),
        )
        return self._read_response(response)

    async def get(self, job_id: str) -> StoredJob | None:
        response = await self._request(
            method="GET", url=self._document_url(job_id), params=[], json_body=None
        )
        if response.status_code == 404:
            return None
        return self._read_response(response)

    async def save(self, job: AgentJob, *, expected: str) -> StoredJob:
        params: QueryParams = [("currentDocument.updateTime", expected)]
        params += [("updateMask.fieldPaths", path) for path in _FIELD_PATHS]
        response = await self._request(
            method="PATCH",
            url=self._document_url(job.job_id),
            params=params,
            json_body=to_document(job),
        )
        return self._read_response(response)


def build_store(
    *,
    mode: str,
    tokens: TokenSource,
    project_id: str,
    database: str,
    collection: str,
    timeout_seconds: float,
    max_attempts: int,
    backoff_seconds: float,
) -> JobStore:
    if mode == "memory":
        return MemoryJobStore()
    return FirestoreJobStore(
        tokens=tokens,
        project_id=project_id,
        database=database,
        collection=collection,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        backoff_seconds=backoff_seconds,
    )
