"""OAuth acces tokens from the Cloud Run metadata server, one cache per scope"""

from __future__ import annotations

import logging
import time
from typing import Final, Protocol

import httpx2

logger = logging.getLogger(__name__)


_METADATA_ROOT: Final = "http://metadata.google.internal/computeMetadata/v1"
_METADATA_TOKEN_URL: Final = f"{_METADATA_ROOT}/instance/service-accounts/default/token"
_METADATA_TIMEOUT_SECONDS: Final = 3.0


_SKEW_SECONDS: Final = 120.0

STORAGE_READ_SCOPE: Final = "https://www.googleapis.com/auth/devstorage.read_only"
DATASTORE_SCOPE: Final = "https://www.googleapis.com/auth/datastore"


class TokenError(RuntimeError):
    """No usable credential. Always retryable - the metadata server comes back."""


class TokenSource(Protocol):
    """Two implementations: the metadata server, and a static test double."""

    def invalidate(self, scope: str) -> None: ...

    async def token(self, client: httpx2.AsyncClient, scope: str) -> str: ...


class MetadataTokenSource:
    """Cache one token per scope for the life of the process."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[str, float]] = {}

    def invalidate(self, scope: str) -> None:
        self._cache.pop(scope, None)

    async def token(self, client: httpx2.AsyncClient, scope: str) -> str:
        cached = self._cache.get(scope)
        if cached is not None and cached[1] - _SKEW_SECONDS > time.monotonic():
            return cached[0]

        try:
            response = await client.get(
                _METADATA_TOKEN_URL,
                params={"scopes": scope},
                headers={"Metadata-Flavor": "Google"},
                timeout=_METADATA_TIMEOUT_SECONDS,
            )
        except httpx2.HTTPError as exc:
            logger.error("metadata server unreachable")
            raise TokenError("credentials are unavailable") from exc

        if response.status_code != 200:
            logger.error(
                "metadata server refused an access token",
                extra={"status": response.status_code},
            )
            raise TokenError("credentials are unavailable")

        payload = response.json()
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise TokenError("credentials are unavailable")

        try:
            lifetime = float(payload.get("expires_in", 0))
        except (TypeError, ValueError):
            lifetime = 0.0
        if lifetime > _SKEW_SECONDS:
            self._cache[scope] = (token, time.monotonic() + lifetime)
        return token


class StaticTokenSource:
    """Local development and tests. Never reaches a network."""

    def __init__(self, token: str = "local-development-token") -> None:  # noqa: S107
        self._token = token

    def invalidate(self, scope: str) -> None:
        del scope

    async def token(self, client: httpx2.AsyncClient, scope: str) -> str:
        del client, scope
        return self._token
