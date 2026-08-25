"""Mesh storage over the raw GCS JSON API.

NO GOOGLE SDK. google-cloud-storage pulls roughly fifteen transitive packages
through `pip-audit --strict` to serve one single-shot upload of one object. The
JSON API is two HTTP calls - a token from the metadata server, then a POST -
and this file is what those two calls cost.

TOKEN SCOPE IS devstorage.read_write, NOT cloud-platform. rinne-reconstruction-sa
holds roles/storage.objectCreator on the bucket and nothing else, and the token
narrows it again at the request level. The web service mints read_only for the
same object. Least privilege twice, deliberately.

ifGenerationMatch=0 MEANS "CREATE ONLY". Reusing a requestId becomes a loud 412
instead of silently overwriting an artifact some Firestore record already points
at - which would be a wrong answer on camera rather than an error.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Final, Protocol
from urllib.parse import quote

import httpx2

logger = logging.getLogger(__name__)

_METADATA_ROOT: Final = "http://metadata.google.internal/computeMetadata/v1"
_METADATA_TOKEN_URL: Final = f"{_METADATA_ROOT}/instance/service-accounts/default/token"
_STORAGE_UPLOAD_URL: Final = "https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
_WRITE_SCOPE: Final = "https://www.googleapis.com/auth/devstorage.read_write"
_GLB_CONTENT_TYPE: Final = "model/gltf-binary"
_METADATA_TIMEOUT_SECONDS: Final = 3.0
_TOKEN_SKEW_SECONDS: Final = 120.0

#: Bound on the in-process test store, so a runaway test cannot eat the heap.
_MEMORY_STORE_LIMIT: Final = 32


class StorageError(RuntimeError):
    """An upload failed. ``rule`` is safe to return to a caller."""

    def __init__(self, rule: str, *, status: int = 502) -> None:
        super().__init__(rule)
        self.rule = rule
        self.status = status


class MeshStore(Protocol):
    """Write-only by design. This service never reads an object back."""

    @property
    def mode(self) -> str: ...

    async def put_glb(self, *, object_name: str, data: bytes) -> str: ...


class MemoryMeshStore:
    """The test path. Keeps the GLB in a bounded map and reports the real URI.

    It reports the gs:// URI it WOULD have written, so a test exercises the
    same contract validation on mesh.uri that production does - the SSRF
    pattern in the schema is checked either way.
    """

    def __init__(self, *, bucket: str) -> None:
        self._bucket = bucket
        self._objects: dict[str, bytes] = {}

    @property
    def mode(self) -> str:
        return "memory"

    @property
    def objects(self) -> dict[str, bytes]:
        return self._objects

    async def put_glb(self, *, object_name: str, data: bytes) -> str:
        if object_name in self._objects:
            # Same semantics as ifGenerationMatch=0, so the duplicate-id path
            # is testable without a network.
            raise StorageError("mesh already exists for this requestId", status=409)
        if len(self._objects) >= _MEMORY_STORE_LIMIT:
            self._objects.clear()
        self._objects[object_name] = data
        return f"gs://{self._bucket}/{object_name}"


class GcsMeshStore:
    """One bucket, create-only, bounded retry."""

    def __init__(
        self,
        *,
        bucket: str,
        max_attempts: int,
        backoff_seconds: float,
        timeout_seconds: float,
    ) -> None:
        self._bucket = bucket
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._timeout_seconds = timeout_seconds
        self._token: str | None = None

    @property
    def mode(self) -> str:
        return "gcs"

    async def _access_token(self, client: httpx2.AsyncClient) -> str:
        if self._token is not None:
            return self._token

        response = await client.get(
            _METADATA_TOKEN_URL,
            params={"scopes": _WRITE_SCOPE},
            headers={"Metadata-Flavor": "Google"},
            timeout=_METADATA_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            # Status only. The body of a failed metadata call echoes request
            # detail, and this one is about a credential.
            logger.error(
                "metadata server refused an access token",
                extra={"status": response.status_code},
            )
            raise StorageError("storage credentials unavailable")

        payload = response.json()
        token = payload.get("access_token")
        expires_in = float(payload.get("expires_in", 0))
        if not isinstance(token, str) or not token:
            raise StorageError("storage credentials unavailable")
        # Only cache a token with usable life left. A near-expired token
        # guarantees a 401 on the next call and an avoidable retry.
        if expires_in > _TOKEN_SKEW_SECONDS:
            self._token = token
        return token

    async def put_glb(self, *, object_name: str, data: bytes) -> str:
        url = _STORAGE_UPLOAD_URL.format(bucket=self._bucket)
        params = {
            "uploadType": "media",
            "name": object_name,
            "ifGenerationMatch": "0",
        }

        async with httpx2.AsyncClient(timeout=self._timeout_seconds) as client:
            last_rule = "mesh upload failed"
            for attempt in range(1, self._max_attempts + 1):
                token = await self._access_token(client)
                response = await client.post(
                    url,
                    params=params,
                    content=data,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": _GLB_CONTENT_TYPE,
                    },
                )

                if response.status_code in (200, 201):
                    return f"gs://{self._bucket}/{quote(object_name, safe='/')}"

                if response.status_code == 412:
                    # Create-only refused: this requestId already has a mesh.
                    # Not retryable, and not a server fault.
                    raise StorageError("mesh already exists for this requestId", status=409)

                if response.status_code == 401:
                    # The cached token is stale. Drop it and let the loop retry
                    # with a fresh one.
                    self._token = None
                    last_rule = "storage credentials rejected"
                elif 400 <= response.status_code < 500:
                    logger.error(
                        "storage refused the upload",
                        extra={"status": response.status_code},
                    )
                    raise StorageError("mesh upload was refused")
                else:
                    last_rule = "mesh upload failed"

                logger.warning(
                    "mesh upload attempt failed",
                    extra={"status": response.status_code, "attempt": attempt},
                )
                if attempt < self._max_attempts:
                    await asyncio.sleep(self._backoff_seconds * attempt)

        raise StorageError(last_rule)


def build_store(
    *,
    mode: str,
    bucket: str,
    max_attempts: int,
    backoff_seconds: float,
    timeout_seconds: float,
) -> MeshStore:
    if mode == "memory":
        return MemoryMeshStore(bucket=bucket)
    return GcsMeshStore(
        bucket=bucket,
        max_attempts=max_attempts,
        backoff_seconds=backoff_seconds,
        timeout_seconds=timeout_seconds,
    )
