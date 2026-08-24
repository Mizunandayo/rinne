# GENERATED FILE - DO NOT EDIT BY HAND.
#
# Source of truth : packages/contracts/schemas
# Regenerate      : pwsh ./packages/contracts/scripts/generate-python.ps1
#
# CI regenerates and runs git diff --exit-code. A schema edit without a
# regeneration is a build failure.

from __future__ import annotations

from enum import IntEnum, StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SchemaVersion(IntEnum):
    """
    Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.
    """

    integer_1 = 1


class Length(StrEnum):
    m = "m"


class Mass(StrEnum):
    kg = "kg"


class Units(BaseModel):
    """
    Declared explicitly so a unit mismatch is a validation error rather than a physics result that is wrong by a factor of a thousand.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    length: Length
    mass: Mass


class Ground(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    friction: float = Field(..., ge=0.0, le=2.0)
    restitution: float = Field(..., ge=0.0, le=1.0)


class Kind(StrEnum):
    tip = "tip"


class Test(BaseModel):
    """
    Which physics test the agent selected. Exactly one, chosen per §7 step 2.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Kind
    push_height_ratio: float = Field(..., alias="pushHeightRatio", ge=0.0, le=1.0)
    """
    Height of the applied push as a fraction of the object's total height.
    """
    force_newtons: float = Field(..., alias="forceNewtons", ge=0.0, le=5000.0)
    direction_degrees: float = Field(..., alias="directionDegrees", ge=0.0, lt=360.0)
    duration_seconds: float | None = Field(
        None, alias="durationSeconds", ge=0.0, le=5.0
    )


class Kind1(StrEnum):
    load = "load"


class Kind2(StrEnum):
    drop = "drop"


class Solver(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    timestep_seconds: float = Field(..., alias="timestepSeconds", ge=0.0005, le=0.05)
    max_steps: int = Field(..., alias="maxSteps", ge=1, le=20000)
    """
    Hard upper bound on simulation steps. §12 forbids unbounded loops, and this is where that rule is enforced for the physics path — the schema makes an unbounded simulation unrepresentable.
    """
    substeps: int | None = Field(None, ge=1, le=16)
    seed: int = Field(..., ge=0, le=4294967295)
    """
    Determinism seed. Both hosts must use it, or the shared-engine claim is unverifiable.
    """


class Source(StrEnum):
    agent = "agent"
    cockpit = "cockpit"
    refit = "refit"
    fixture = "fixture"


class Provenance(BaseModel):
    """
    Where the estimates in this document came from. Read by the confidence gate in §7 step 3.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    source: Source
    estimated_by: str | None = Field(None, alias="estimatedBy", max_length=64)
    reconstruction_confidence: float | None = Field(
        None, alias="reconstructionConfidence", ge=0.0, le=1.0
    )
    material_confidence: float | None = Field(
        None, alias="materialConfidence", ge=0.0, le=1.0
    )
    refit_iteration: int | None = Field(None, alias="refitIteration", ge=0, le=6)


class Vec3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    x: float = Field(..., ge=-1000.0, le=1000.0)
    y: float = Field(..., ge=-1000.0, le=1000.0)
    z: float = Field(..., ge=-1000.0, le=1000.0)


class Format(StrEnum):
    glb = "glb"


class MeshRef(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    uri: str = Field(..., pattern="^gs://[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]/.{1,512}$")
    """
    gs:// ONLY. The physics service fetches this URI, and this document is shaped by model output, so an unrestricted scheme here is a server-side request forgery primitive pointed at the metadata server. Restricting the scheme in the schema kills that class of attack at the contract boundary rather than in a handler someone might forget to write.
    """
    format: Format
    sha256: str | None = Field(None, pattern="^[a-f0-9]{64}$")
    """
    Integrity check on the fetched asset. Optional on Day 3, required once the cockpit and the agent fetch the same mesh.
    """


class RigidBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mesh: MeshRef
    mass_kilograms: float = Field(..., alias="massKilograms", gt=0.0, le=5000.0)
    center_of_mass: Vec3 | None = Field(None, alias="centerOfMass")
    friction: float = Field(..., ge=0.0, le=2.0)
    restitution: float = Field(..., ge=0.0, le=1.0)
    linear_damping: float | None = Field(None, alias="linearDamping", ge=0.0, le=10.0)
    angular_damping: float | None = Field(None, alias="angularDamping", ge=0.0, le=10.0)
    initial_translation: Vec3 = Field(..., alias="initialTranslation")
    initial_rotation_degrees: Vec3 | None = Field(None, alias="initialRotationDegrees")


class Test1(BaseModel):
    """
    Which physics test the agent selected. Exactly one, chosen per §7 step 2.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Kind1
    load_kilograms: float = Field(..., alias="loadKilograms", ge=0.0, le=2000.0)
    contact_radius: float = Field(..., alias="contactRadius", ge=0.0, le=5.0)
    offset_from_center: Vec3 | None = Field(None, alias="offsetFromCenter")


class Test2(BaseModel):
    """
    Which physics test the agent selected. Exactly one, chosen per §7 step 2.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Kind2
    drop_height_meters: float = Field(..., alias="dropHeightMeters", ge=0.0, le=20.0)
    initial_rotation_degrees: Vec3 | None = Field(None, alias="initialRotationDegrees")


class SceneDescription(BaseModel):
    """
    Portable, engine-agnostic physics scene. This is the single interchange format between the browser Rapier build, the headless Node Rapier build, and the Python agent, and it is also the exportable simulation artifact. Two hosts given the same document must produce the same result; anything that would let them diverge does not belong in this file.
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
    Stable identifier, also used as the Firestore document key.
    """
    units: Units
    """
    Declared explicitly so a unit mismatch is a validation error rather than a physics result that is wrong by a factor of a thousand.
    """
    gravity: Vec3
    ground: Ground
    body: RigidBody
    test: Test | Test1 | Test2
    """
    Which physics test the agent selected. Exactly one, chosen per §7 step 2.
    """
    solver: Solver
    provenance: Provenance | None = None
    """
    Where the estimates in this document came from. Read by the confidence gate in §7 step 3.
    """
