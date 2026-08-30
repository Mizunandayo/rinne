"""A ReconstructionResult plus a chosen test becomes one contract-valid SceneDescription."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from rinne_agent.contracts import ReconstructionResult, SceneDescription

_GRAVITY: Final = 9.81

#: Section 0c measured the tipping boundary on a 2.4kg hull at 12N, which is
#: 0.51 of its weight. A force fixed in newtons is meaningless across masses, so
#: the push is scaled to the body and this ratio sits on the measured boundary.
_DEFAULT_TIP_FORCE_RATIO: Final = 0.5


@dataclass(frozen=True)
class SolverSettings:
    """Both hosts must agree on these or the shared-engine claim is unverifiable."""

    timestep_seconds: float
    max_steps: int
    seed: int
    ground_friction: float
    ground_restitution: float
    tip_force_ratio: float
    tip_height_ratio: float
    tip_direction_degrees: float
    tip_duration_seconds: float
    drop_height_meters: float
    load_multiple: float


def _test_block(kind: str, result: ReconstructionResult, s: SolverSettings) -> dict[str, Any]:
    mass = result.material.mass_kilograms
    if kind == "load":
        footprint = min(result.mesh.extent.x, result.mesh.extent.z)
        return {
            "kind": "load",
            "loadKilograms": round(min(mass * s.load_multiple, 2000.0), 4),
            "contactRadius": round(max(footprint * 0.25, 0.001), 4),
        }
    if kind == "drop":
        return {"kind": "drop", "dropHeightMeters": s.drop_height_meters}
    return {
        "kind": "tip",
        "pushHeightRatio": s.tip_height_ratio,
        "forceNewtons": round(min(mass * _GRAVITY * s.tip_force_ratio, 5000.0), 4),
        "directionDegrees": s.tip_direction_degrees,
        "durationSeconds": s.tip_duration_seconds,
    }


def build(
    *,
    job_id: str,
    result: ReconstructionResult,
    kind: str,
    settings: SolverSettings,
) -> SceneDescription:
    """The sceneId is the jobId, so a scene traces back to the decision that made it."""
    resting = 0.0 if kind != "drop" else settings.drop_height_meters
    mesh: dict[str, Any] = {"uri": result.mesh.uri, "format": "glb"}
    if result.mesh.sha256:
        mesh["sha256"] = result.mesh.sha256

    return SceneDescription.model_validate(
        {
            "schemaVersion": 1,
            "sceneId": job_id,
            "units": {"length": "m", "mass": "kg"},
            "gravity": {"x": 0.0, "y": -_GRAVITY, "z": 0.0},
            "ground": {
                "friction": settings.ground_friction,
                "restitution": settings.ground_restitution,
            },
            "body": {
                "mesh": mesh,
                "massKilograms": result.material.mass_kilograms,
                "friction": result.material.friction,
                "restitution": result.material.restitution,
                # Normalisation already seats the mesh at y=0, so a non-drop test
                # starts exactly where the reconstruction left it.
                "initialTranslation": {"x": 0.0, "y": resting, "z": 0.0},
            },
            "test": _test_block(kind, result, settings),
            "solver": {
                "timestepSeconds": settings.timestep_seconds,
                "maxSteps": settings.max_steps,
                "seed": settings.seed,
            },
            "provenance": {
                "source": "agent",
                "estimatedBy": result.pipeline.name,
                "reconstructionConfidence": result.confidence.score,
                "materialConfidence": result.material.confidence,
            },
        }
    )
