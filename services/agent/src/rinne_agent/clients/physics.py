"""POST /v1/simulate on rinne-physics, with an ID token."""

from __future__ import annotations

import logging
import time
from typing import Protocol

import httpx2
from pydantic import ValidationError

from rinne_agent.contracts import SceneDescription, SimulationResult
from rinne_agent.contracts.agent_job import JobActor
from rinne_agent.errors import RuleError
from rinne_agent.gcp.tokens import TokenError, TokenSource

logger = logging.getLogger(__name__)


class Simulator(Protocol):
    """Two implementations: the live Fastify service, and an offline double."""

    async def simulate(self, scene: SceneDescription) -> tuple[SimulationResult, int]: ...


class HttpSimulator:
    """The scene is sent by alias, because the contract is camelCase on the wire."""

    def __init__(self, *, base_url: str, tokens: TokenSource, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._tokens = tokens
        self._timeout_seconds = timeout_seconds

    async def simulate(self, scene: SceneDescription) -> tuple[SimulationResult, int]:
        started = time.perf_counter()
        body = scene.model_dump(mode="json", by_alias=True, exclude_none=True)

        async with httpx2.AsyncClient(timeout=self._timeout_seconds) as client:
            try:
                token = await self._tokens.identity(client, self._base_url)
            except TokenError as exc:
                raise RuleError(
                    "physics credentials are unavailable",
                    retryable=True,
                    actor=JobActor.physics,
                ) from exc

            try:
                response = await client.post(
                    f"{self._base_url}/v1/simulate",
                    headers={"Authorization": f"Bearer {token}"},
                    json=body,
                )
            except httpx2.HTTPError as exc:
                raise RuleError(
                    "the physics service is unreachable",
                    retryable=True,
                    actor=JobActor.physics,
                ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code != 200:
            logger.error("simulation refused", extra={"status": response.status_code})
            raise RuleError(
                "the physics service refused the scene",
                retryable=response.status_code >= 500,
                actor=JobActor.physics,
            )

        try:
            return SimulationResult.model_validate(response.json()), latency_ms
        except (ValidationError, ValueError) as exc:
            raise RuleError(
                "the physics service returned an unusable result",
                retryable=False,
                actor=JobActor.physics,
            ) from exc


class StubSimulator:
    """The test path. verdict and notices are settable so the gate can be driven."""

    def __init__(self, *, verdict: str = "stable", notices: list[str] | None = None) -> None:
        self._verdict = verdict
        self._notices = notices or []

    async def simulate(self, scene: SceneDescription) -> tuple[SimulationResult, int]:
        return (
            SimulationResult.model_validate(
                {
                    "schemaVersion": 1,
                    "sceneId": scene.scene_id,
                    "completedAt": "2026-08-30T00:00:00Z",
                    "host": {
                        "runtime": "node",
                        "engine": "rapier3d-compat",
                        "engineVersion": "0.14.0",
                    },
                    "outcome": {
                        "verdict": self._verdict,
                        "settled": self._verdict != "inconclusive",
                        "steps": 240,
                        "simulatedSeconds": 4.0,
                        "tiltDegrees": 0.97 if self._verdict == "stable" else 90.32,
                        "driftMeters": 0.004,
                    },
                    "finalPose": {
                        "translation": {"x": 0.0, "y": 0.05, "z": 0.0},
                        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                    },
                    "collider": {
                        "kind": "convex-hull",
                        "sourceVertices": 3752,
                        "hullVertices": 152,
                        "massKilograms": scene.body.mass_kilograms,
                    },
                    "determinism": {
                        "seed": scene.solver.seed,
                        "timestepSeconds": scene.solver.timestep_seconds,
                        "substeps": 1,
                        "digest": "2aa41a6cdf3d89f5",
                    },
                    "timings": {"setupMs": 1, "stepMs": 1, "totalMs": 2},
                    "notices": [
                        {"code": code, "severity": "warning", "message": "Stub notice."}
                        for code in self._notices
                    ],
                }
            ),
            0,
        )


def build_simulator(
    *, mode: str, base_url: str, tokens: TokenSource, timeout_seconds: float
) -> Simulator:
    if mode == "memory":
        return StubSimulator()
    if not base_url:
        raise RuntimeError("client_mode=http requires a physics service URL")
    return HttpSimulator(base_url=base_url, tokens=tokens, timeout_seconds=timeout_seconds)
