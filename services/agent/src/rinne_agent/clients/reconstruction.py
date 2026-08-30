"""POST /v1/reconstruct on rinne-reconstruction, over multipart, with an ID token."""

from __future__ import annotations

import json
import logging
import time
from typing import Protocol

import httpx2
from pydantic import ValidationError

from rinne_agent.contracts import ReconstructionResult
from rinne_agent.contracts.agent_job import JobActor
from rinne_agent.errors import RuleError
from rinne_agent.gcp.tokens import TokenError, TokenSource

logger = logging.getLogger(__name__)


class Reconstructor(Protocol):
    """Two implementations: the live GPU service, and an offline double."""

    async def reconstruct(
        self, *, request_id: str, image: bytes, mime_type: str
    ) -> tuple[ReconstructionResult, int]: ...


class HttpReconstructor:
    """One call. The L4 is max-instances 1, so this serialises with the cockpit."""

    def __init__(self, *, base_url: str, tokens: TokenSource, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._tokens = tokens
        self._timeout_seconds = timeout_seconds

    async def reconstruct(
        self, *, request_id: str, image: bytes, mime_type: str
    ) -> tuple[ReconstructionResult, int]:
        started = time.perf_counter()
        document = json.dumps({"schemaVersion": 1, "requestId": request_id})

        async with httpx2.AsyncClient(timeout=self._timeout_seconds) as client:
            try:
                token = await self._tokens.identity(client, self._base_url)
            except TokenError as exc:
                raise RuleError(
                    "reconstruction credentials are unavailable",
                    retryable=True,
                    actor=JobActor.reconstruction,
                ) from exc

            try:
                response = await client.post(
                    f"{self._base_url}/v1/reconstruct",
                    headers={"Authorization": f"Bearer {token}"},
                    data={"request": document},
                    files=[("images", (f"{request_id}.img", image, mime_type))],
                )
            except httpx2.HTTPError as exc:
                raise RuleError(
                    "the reconstruction service is unreachable",
                    retryable=True,
                    actor=JobActor.reconstruction,
                ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code == 409:
            raise RuleError(
                "a mesh already exists for this scan",
                retryable=False,
                actor=JobActor.reconstruction,
            )
        if response.status_code != 200:
            logger.error("reconstruction refused", extra={"status": response.status_code})
            raise RuleError(
                "the reconstruction service refused the scan",
                retryable=response.status_code >= 500,
                actor=JobActor.reconstruction,
            )

        try:
            return ReconstructionResult.model_validate(response.json()), latency_ms
        except (ValidationError, ValueError) as exc:
            raise RuleError(
                "the reconstruction service returned an unusable result",
                retryable=False,
                actor=JobActor.reconstruction,
            ) from exc


class StubReconstructor:
    """The test path. Every field is real and contract-valid; only the mesh is invented."""

    def __init__(self, *, confidence: float = 0.82, material_confidence: float = 0.60) -> None:
        self._confidence = confidence
        self._material_confidence = material_confidence

    async def reconstruct(
        self, *, request_id: str, image: bytes, mime_type: str
    ) -> tuple[ReconstructionResult, int]:
        del image, mime_type
        weights = {"fieldDecisiveness": 0.45, "watertightness": 0.30, "volumePlausibility": 0.10}
        return (
            ReconstructionResult.model_validate(
                {
                    "schemaVersion": 1,
                    "requestId": request_id,
                    "completedAt": "2026-08-30T00:00:00Z",
                    "mesh": {
                        "uri": f"gs://rinne-artifacts-rinnehackathon/meshes/{request_id}.glb",
                        "format": "glb",
                        "byteLength": 4096,
                        "vertexCount": 512,
                        "faceCount": 1024,
                        "watertight": True,
                        "extent": {"x": 0.12, "y": 0.30, "z": 0.09},
                        "volumeCubicMeters": 0.0016,
                        "upAxis": "y",
                        "scaleBasis": "assumed",
                    },
                    "material": {
                        "name": "wood",
                        "basis": "heuristic-v1",
                        "confidence": self._material_confidence,
                        "densityKilogramsPerCubicMeter": 600,
                        "massKilograms": 0.528,
                        "friction": 0.5,
                        "restitution": 0.2,
                    },
                    "confidence": {
                        "score": self._confidence,
                        "band": "high" if self._confidence >= 0.7 else "low",
                        "calibrated": False,
                        "components": {**weights, "foregroundQuality": 0.5},
                        "weights": {**weights, "foregroundQuality": 0.15},
                    },
                    "pipeline": {"name": "stub", "version": "0.1.0", "device": "cpu"},
                    "images": {
                        "received": 1,
                        "accepted": 1,
                        "used": 1,
                        "reencoded": True,
                        "longestEdgePixels": 1024,
                    },
                    "timings": {
                        "validationMs": 1,
                        "inferenceMs": 1,
                        "meshMs": 1,
                        "uploadMs": 1,
                        "totalMs": 4,
                    },
                }
            ),
            0,
        )


def build_reconstructor(
    *, mode: str, base_url: str, tokens: TokenSource, timeout_seconds: float
) -> Reconstructor:
    if mode == "memory":
        return StubReconstructor()
    if not base_url:
        raise RuntimeError("client_mode=http requires a reconstruction service URL")
    return HttpReconstructor(base_url=base_url, tokens=tokens, timeout_seconds=timeout_seconds)
