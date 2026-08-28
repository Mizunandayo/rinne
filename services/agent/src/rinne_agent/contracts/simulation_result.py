# GENERATED FILE - DO NOT EDIT BY HAND.
#
# Source of truth : packages/contracts/schemas
# Regenerate      : pwsh ./packages/contracts/scripts/generate-python.ps1
#
# CI regenerates and runs git diff --exit-code. A schema edit without a
# regeneration is a build failure.

from __future__ import annotations

from enum import IntEnum, StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class SchemaVersion(IntEnum):
    """
    Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.
    """

    integer_1 = 1


class Runtime(StrEnum):
    node = "node"
    browser = "browser"


class Engine(StrEnum):
    rapier3d_compat = "rapier3d-compat"


class SimulationHost(BaseModel):
    """
    Which side ran it. This is the only field that is allowed to differ between two runs of the same scene, and it exists so that a parity comparison can say which two things it compared.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    runtime: Runtime
    engine: Engine
    engine_version: str = Field(..., alias="engineVersion", max_length=32, min_length=1)


class Verdict(StrEnum):
    """
    stable: settled within tolerance of where it started. tipped: settled with its up-axis more than 45 degrees from vertical. slid: settled upright but displaced more than a quarter of its longest edge. inconclusive: never settled inside solver.maxSteps, which is a real answer about the scene and not an error.
    """

    stable = "stable"
    tipped = "tipped"
    slid = "slid"
    inconclusive = "inconclusive"


class SimulationOutcome(BaseModel):
    """
    The answer, plus the two measurements it was derived from. verdict is a closed enum so the agent can branch on it; tiltDegrees and driftMeters are reported so a human can see why it said that.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    verdict: Verdict
    """
    stable: settled within tolerance of where it started. tipped: settled with its up-axis more than 45 degrees from vertical. slid: settled upright but displaced more than a quarter of its longest edge. inconclusive: never settled inside solver.maxSteps, which is a real answer about the scene and not an error.
    """
    settled: bool
    """
    True when the pose stopped changing for a full settle window. Deliberately not a velocity test: a convex hull resting on a plane keeps a small non-zero angular velocity indefinitely without moving.
    """
    steps: int = Field(..., ge=0, le=20000)
    simulated_seconds: float = Field(..., alias="simulatedSeconds", ge=0.0, le=1000.0)
    tilt_degrees: float = Field(..., alias="tiltDegrees", ge=0.0, le=180.0)
    """
    Angle between the body's local +Y after simulation and world +Y. Yaw does not count as tilt, which is why this is measured from the up-axis rather than from the quaternion's angle.
    """
    drift_meters: float = Field(..., alias="driftMeters", ge=0.0, le=100000.0)
    """
    Horizontal distance from the initial translation. Vertical motion is excluded: a body settling onto the ground moves down, and that is not drift.
    """


class PoseVector(BaseModel):
    """
    Metres. Not named vec3: every definitions key becomes a flat top-level TypeScript identifier and scene-description.schema.json already owns that name.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    x: float = Field(..., ge=-100000.0, le=100000.0)
    y: float = Field(..., ge=-100000.0, le=100000.0)
    z: float = Field(..., ge=-100000.0, le=100000.0)


class PoseRotation(BaseModel):
    """
    Unit quaternion, Rapier's own component order.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    x: float = Field(..., ge=-1.0, le=1.0)
    y: float = Field(..., ge=-1.0, le=1.0)
    z: float = Field(..., ge=-1.0, le=1.0)
    w: float = Field(..., ge=-1.0, le=1.0)


class Kind(StrEnum):
    convex_hull = "convex-hull"


class ColliderSummary(BaseModel):
    """
    What the mesh actually became. A reconstruction is not convex and this says so in the payload rather than in a comment.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Kind
    source_vertices: int = Field(..., alias="sourceVertices", ge=0, le=10000000)
    hull_vertices: int = Field(..., alias="hullVertices", ge=0, le=100000)
    """
    After voxel decimation. A hull built from every reconstruction vertex has hundreds of near-coplanar faces, its contact manifold flickers every step, and the body then never comes to rest - so decimation is a correctness requirement, not an optimisation.
    """
    mass_kilograms: float = Field(..., alias="massKilograms", gt=0.0, le=5000.0)


class DeterminismRecord(BaseModel):
    """
    Everything needed to reproduce this run, plus the digest that makes two runs comparable in one string. The digest covers the scene id, the solver settings, the verdict, the step count and the final pose at 6dp. It excludes completedAt and the host block by design.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    seed: int = Field(..., ge=0, le=4294967295)
    timestep_seconds: float = Field(..., alias="timestepSeconds", ge=0.0005, le=0.05)
    substeps: int = Field(..., ge=1, le=16)
    digest: str = Field(..., pattern="^[a-f0-9]{16}$")
    """
    FNV-1a 64 over the canonical form, as 16 lowercase hex characters. Not a cryptographic hash and not a security control: it is a comparison key that has to compute identically and synchronously in Node and in a browser, which rules out both node:crypto and the async crypto.subtle.
    """


class SimulationTimings(BaseModel):
    """
    Wall-clock milliseconds. Not named stageTimings: reconstruction-result.schema.json already owns that name.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    setup_ms: int = Field(..., alias="setupMs", ge=0, le=600000)
    step_ms: int = Field(..., alias="stepMs", ge=0, le=600000)
    total_ms: int = Field(..., alias="totalMs", ge=0, le=600000)


class Code(StrEnum):
    collider_is_convex_hull = "collider-is-convex-hull"
    collider_decimated = "collider-decimated"
    center_of_mass_not_applied = "center-of-mass-not-applied"
    did_not_settle = "did-not-settle"
    left_the_ground_plane = "left-the-ground-plane"
    load_test_not_implemented = "load-test-not-implemented"


class Severity(StrEnum):
    info = "info"
    warning = "warning"


class SimulationNotice(BaseModel):
    """
    One caveat about this result. The code is a closed enum so a consumer can branch on it; the message is a fixed sentence for a human.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    code: Code
    severity: Severity
    message: str = Field(..., max_length=200, min_length=1)


class BodyPose(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    translation: PoseVector
    rotation: PoseRotation


class SimulationResult(BaseModel):
    """
    What one SceneDescription produced when it was simulated. The same scene document handed to the browser build and to the headless Node build must produce the same determinism.digest; that equality is the shared-engine claim, and parity.test.ts asserts it. Nothing host-specific belongs in this file except the host block itself, which exists precisely so a reader can tell which side produced the document.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: SchemaVersion = Field(..., alias="schemaVersion")
    """
    Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.
    """
    scene_id: str = Field(..., alias="sceneId", pattern="^[a-z0-9][a-z0-9-]{7,63}$")
    """
    Echoed from the SceneDescription that produced this result.
    """
    completed_at: AwareDatetime = Field(..., alias="completedAt")
    """
    RFC 3339 timestamp taken after the last step. Deliberately NOT part of the determinism digest - a wall clock is the one thing two hosts can never agree on.
    """
    host: SimulationHost
    outcome: SimulationOutcome
    final_pose: BodyPose = Field(..., alias="finalPose")
    collider: ColliderSummary
    determinism: DeterminismRecord
    timings: SimulationTimings
    notices: list[SimulationNotice] | None = Field(None, max_length=8)
    """
    Bounded list of things the caller should know about this result - an unsettled body, a centre of mass that could not be applied, a decimated collider. Named rules, never library messages.
    """
