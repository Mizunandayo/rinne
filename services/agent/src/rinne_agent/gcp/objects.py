"""Reading one scan object out of GCS, bounded, over the raw JSON API."""

from __future__ import annotations

import base64
import logging
from typing import Final, Protocol
from urllib.parse import quote

import httpx2

from rinne_agent.errors import RuleError
from rinne_agent.gcp.tokens import STORAGE_READ_SCOPE, TokenError, TokenSource

logger = logging.getLogger(__name__)

_OBJECT_URL: Final = "https://storage.googleapis.com/storage/v1/b/{bucket}/o/{object_name}"


_MAGIC: Final[dict[str, tuple[bytes, ...]]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


_ONE_PIXEL_PNG: Final = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def check_magic(data: bytes, content_type: str) -> None:
    """Reject bytes that do not begin the way the declared type requires."""
    prefixes = _MAGIC.get(content_type)
    if prefixes is None or not any(data.startswith(prefix) for prefix in prefixes):
        raise RuleError("scan bytes do not match the declared image type", retryable=False)
    if content_type == "image/webp" and data[8:12] != b"WEBP":
        raise RuleError("scan bytes do not match the declared image type", retryable=False)


class ScanReader(Protocol):
    """Two implementations: the GCS JSON API, and an in-process test double."""

    async def read(self, *, bucket: str, object_name: str, generation: str) -> bytes: ...


class MemoryObjectReader:
    """The test path. Returns real PNG bytes so nothing downstream is faked."""

    def __init__(self, *, default: bytes = _ONE_PIXEL_PNG) -> None:
        self._default = default
        self._objects: dict[tuple[str, str, str], bytes] = {}

    def put(self, *, bucket: str, object_name: str, generation: str, data: bytes) -> None:
        self._objects[(bucket, object_name, generation)] = data

    async def read(self, *, bucket: str, object_name: str, generation: str) -> bytes:
        return self._objects.get((bucket, object_name, generation), self._default)


class ObjectReader:
    """One bucket, read-only, one object at a time."""

    def __init__(self, *, tokens: TokenSource, timeout_seconds: float, max_bytes: int) -> None:
        self._tokens = tokens
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes

    async def read(self, *, bucket: str, object_name: str, generation: str) -> bytes:
        url = _OBJECT_URL.format(bucket=bucket, object_name=quote(object_name, safe=""))
        params = {"alt": "media", "generation": generation}

        async with httpx2.AsyncClient(timeout=self._timeout_seconds) as client:
            try:
                token = await self._tokens.token(client, STORAGE_READ_SCOPE)
            except TokenError as exc:
                raise RuleError("scan storage credentials are unavailable", retryable=True) from exc

            try:
                response = await client.get(
                    url, params=params, headers={"Authorization": f"Bearer {token}"}
                )
            except httpx2.HTTPError as exc:
                raise RuleError("the scan object could not be read", retryable=True) from exc

            if response.status_code == 401:
                self._tokens.invalidate(STORAGE_READ_SCOPE)
                raise RuleError("scan storage credentials were rejected", retryable=True)
            if response.status_code == 404:
                raise RuleError("the scan object no longer exists", retryable=False)
            if 400 <= response.status_code < 500:
                logger.error("storage refused the read", extra={"status": response.status_code})
                raise RuleError("the scan object could not be read", retryable=False)
            if response.status_code != 200:
                logger.warning("storage read failed", extra={"status": response.status_code})
                raise RuleError("the scan object could not be read", retryable=True)

            data = response.content

        if len(data) > self._max_bytes:
            raise RuleError("the scan object exceeds the size limit", retryable=False)
        if not data:
            raise RuleError("the scan object is empty", retryable=False)
        return data


def build_reader(
    *,
    mode: str,
    tokens: TokenSource,
    timeout_seconds: float,
    max_bytes: int,
) -> ScanReader:
    if mode == "memory":
        return MemoryObjectReader()
    return ObjectReader(tokens=tokens, timeout_seconds=timeout_seconds, max_bytes=max_bytes)
