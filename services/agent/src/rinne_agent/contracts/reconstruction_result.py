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


class Format(StrEnum):
    glb = "glb"


class UpAxis(StrEnum):
    """
    Y, always. Marching cubes emits Z-up; normalisation rotates it once here so no consumer has to guess.
    """

    y = "y"


class ScaleBasis(StrEnum):
    """
    assumed: scale came from assumedLongestDimensionMeters and is a guess. measured: scale came from a fiducial marker of known size. Day 7 flips this value with no contract change, which is the entire reason it is an enum and not a boolean.
    """

    assumed = "assumed"
    measured = "measured"


class MeshExtent(BaseModel):
    """
    Axis-aligned bounding box dimensions in metres, after normalisation. Not named vec3: every definitions key becomes a flat top-level TypeScript identifier and scene-description.schema.json already owns that name.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    x: float = Field(..., ge=0.0, le=100.0)
    y: float = Field(..., ge=0.0, le=100.0)
    z: float = Field(..., ge=0.0, le=100.0)


class Name(StrEnum):
    cardboard = "cardboard"
    wood = "wood"
    plastic = "plastic"
    metal = "metal"
    glass = "glass"
    fabric = "fabric"
    unknown = "unknown"


class Basis(StrEnum):
    """
    How the guess was made. heuristic-v1 is the mean-vertex-colour HSV classifier. flash-vision-v1 is the Gemini Flash call that replaces it on Day 4 - it is in the enum now so that swap is a config change rather than a contract change.
    """

    heuristic_v1 = "heuristic-v1"
    flash_vision_v1 = "flash-vision-v1"


class MaterialEstimate(BaseModel):
    """
    The physical properties the physics service needs, plus how confident the service is that they are right. The confidences are low on purpose: a weak material signal SHOULD push a borderline job into escalation rather than quietly through it.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Name
    basis: Basis
    """
    How the guess was made. heuristic-v1 is the mean-vertex-colour HSV classifier. flash-vision-v1 is the Gemini Flash call that replaces it on Day 4 - it is in the enum now so that swap is a config change rather than a contract change.
    """
    confidence: float = Field(..., ge=0.0, le=1.0)
    density_kilograms_per_cubic_meter: float = Field(
        ..., alias="densityKilogramsPerCubicMeter", gt=0.0, le=25000.0
    )
    mass_kilograms: float = Field(..., alias="massKilograms", gt=0.0, le=5000.0)
    """
    density * max(volume * solidFraction, 1e-6), capped at 5000 and floored at 1e-4. The bounds match rigidBody.massKilograms so a result drops straight into a SceneDescription.
    """
    friction: float = Field(..., ge=0.0, le=2.0)
    restitution: float = Field(..., ge=0.0, le=1.0)


class Band(StrEnum):
    """
    Coarse bucket for the UI and for the escalation decision. The thresholds are documented guesses in config until Day 3 measures them against three real objects, which is what calibrated reports.
    """

    low = "low"
    medium = "medium"
    high = "high"


class ConfidenceComponents(BaseModel):
    """
    Each component is measured, in [0,1], and rounded to 4dp so tests are deterministic. foregroundQuality is OPTIONAL because it derives from the segmentation mask, which ships with TripoSR; a build without segmentation omits the key entirely rather than inventing a value for it.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_decisiveness: float = Field(..., alias="fieldDecisiveness", ge=0.0, le=1.0)
    """
    How far the density field sat from the iso-surface, sampled one voxel in 64 by the marching-cubes shim. A field that hovers near the threshold everywhere produced a surface that could have gone either way.
    """
    watertightness: float = Field(..., ge=0.0, le=1.0)
    """
    1.0 for a closed surface, otherwise scaled by the share of boundary edges - rows of edges_sorted appearing exactly once.
    """
    volume_plausibility: float = Field(..., alias="volumePlausibility", ge=0.0, le=1.0)
    """
    Occupancy of the bounding box, through a triangular window peaking at 0.5 and reaching zero at 0.03 and 1.0. Catches both the wisp and the solid block.
    """
    foreground_quality: float | None = Field(
        None, alias="foregroundQuality", ge=0.0, le=1.0
    )
    """
    framing * cropping, from the segmentation mask. Absent until segmentation ships, at which point the weights below regain their fourth entry.
    """


class ConfidenceWeights(BaseModel):
    """
    The exact weights used for THIS response. They sum to 1.0, and they change when a component is added or removed - which is precisely why they are transmitted rather than documented. Same optionality as the components: no foregroundQuality weight without a foregroundQuality component.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_decisiveness: float = Field(..., alias="fieldDecisiveness", ge=0.0, le=1.0)
    watertightness: float = Field(..., ge=0.0, le=1.0)
    volume_plausibility: float = Field(..., alias="volumePlausibility", ge=0.0, le=1.0)
    foreground_quality: float | None = Field(
        None, alias="foregroundQuality", ge=0.0, le=1.0
    )


class Name1(StrEnum):
    """
    stub: a deterministic procedural mesh, honest about being one. triposr: single-image feed-forward, fast and coarse. instantmesh: multi-view diffusion into a sparse-view reconstruction, slower and far cleaner. Which one ran is a property of the result, not of the deployment, because the document has to stay readable long after the environment changed.
    """

    stub = "stub"
    triposr = "triposr"
    instantmesh = "instantmesh"


class Device(StrEnum):
    cpu = "cpu"
    cuda = "cuda"


class PipelineInfo(BaseModel):
    """
    Which reconstructor actually ran. This exists so a placeholder can say it is a placeholder, in the payload, without anybody having to remember to mention it.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Name1
    """
    stub: a deterministic procedural mesh, honest about being one. triposr: single-image feed-forward, fast and coarse. instantmesh: multi-view diffusion into a sparse-view reconstruction, slower and far cleaner. Which one ran is a property of the result, not of the deployment, because the document has to stay readable long after the environment changed.
    """
    version: str = Field(..., max_length=64, min_length=1)
    """
    Pipeline build identifier. For triposr this is the pinned upstream commit SHA, which is what makes vendoring at a known state a truthful claim rather than a hope.
    """
    device: Device
    seed: int | None = Field(None, ge=0, le=4294967295)
    """
    Determinism seed, when the pipeline takes one. Same role as SceneDescription.solver.seed.
    """


class ImageAccounting(BaseModel):
    """
    What happened to the uploaded images. reencoded is the visible proof of validation layer 7: the model never saw a byte the client sent, which is what strips EXIF GPS and kills polyglot payloads.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    received: int = Field(..., ge=1, le=4)
    accepted: int = Field(..., ge=0, le=4)
    used: int = Field(..., ge=0, le=4)
    """
    How many accepted images the pipeline actually consumed. Day 2 accepts up to four and uses the first; that narrowing is behaviour inside an unchanged contract, and this field is where it is admitted.
    """
    reencoded: bool
    longest_edge_pixels: int = Field(..., alias="longestEdgePixels", ge=1, le=8192)
    """
    Longest edge of the re-encoded image handed to the pipeline, after the bound in max_image_edge.
    """


class StageTimings(BaseModel):
    """
    Wall-clock milliseconds per stage. Read on camera, and the cheapest way to see a cold GPU start for what it is.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    validation_ms: int = Field(..., alias="validationMs", ge=0, le=600000)
    inference_ms: int = Field(..., alias="inferenceMs", ge=0, le=600000)
    mesh_ms: int = Field(..., alias="meshMs", ge=0, le=600000)
    upload_ms: int = Field(..., alias="uploadMs", ge=0, le=600000)
    total_ms: int = Field(..., alias="totalMs", ge=0, le=600000)


class Code(StrEnum):
    stub_pipeline = "stub-pipeline"
    scale_assumed = "scale-assumed"
    confidence_uncalibrated = "confidence-uncalibrated"
    foreground_quality_unavailable = "foreground-quality-unavailable"
    images_ignored = "images-ignored"
    material_weak_signal = "material-weak-signal"
    low_face_count = "low-face-count"
    mesh_not_watertight = "mesh-not-watertight"


class Severity(StrEnum):
    info = "info"
    warning = "warning"


class ReconstructionNotice(BaseModel):
    """
    One caveat about this result. The code is a closed enum so a consumer can branch on it; the message is for a human and is a fixed sentence, never a library string, a filename, or a byte range.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    code: Code
    severity: Severity
    message: str = Field(..., max_length=200, min_length=1)


class ReconstructedMesh(BaseModel):
    """
    The stored artifact plus the measurements taken from it. The physics service and the agent both read these, so they live in the contract rather than being recomputed twice and disagreeing.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    uri: str = Field(..., pattern="^gs://[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]/.{1,512}$")
    """
    gs:// ONLY, matching the meshRef precedent in scene-description.schema.json. The physics service fetches this URI and this document is shaped by model output, so an unrestricted scheme here is a server-side request forgery primitive pointed at the metadata server. Restricting the scheme at the contract boundary kills that class of attack once, rather than in every handler that might forget.
    """
    format: Format
    sha256: str | None = Field(None, pattern="^[a-f0-9]{64}$")
    """
    Integrity check on the stored asset, computed over the exact bytes uploaded.
    """
    byte_length: int = Field(..., alias="byteLength", ge=1, le=104857600)
    """
    Size of the stored GLB, so a viewer can budget its fetch before starting it.
    """
    vertex_count: int = Field(..., alias="vertexCount", ge=0, le=10000000)
    face_count: int = Field(..., alias="faceCount", ge=0, le=10000000)
    watertight: bool
    """
    Reported by trimesh AFTER normalisation. Marching cubes routinely produces duplicate vertices and degenerate faces, either of which makes a genuinely closed surface report false, so this is measured post-merge or it is meaningless.
    """
    extent: MeshExtent
    volume_cubic_meters: float = Field(
        ..., alias="volumeCubicMeters", ge=0.0, le=1000.0
    )
    """
    Signed volume magnitude of the normalised mesh. Feeds volumePlausibility and the mass estimate.
    """
    up_axis: UpAxis = Field(..., alias="upAxis")
    """
    Y, always. Marching cubes emits Z-up; normalisation rotates it once here so no consumer has to guess.
    """
    scale_basis: ScaleBasis = Field(..., alias="scaleBasis")
    """
    assumed: scale came from assumedLongestDimensionMeters and is a guess. measured: scale came from a fiducial marker of known size. Day 7 flips this value with no contract change, which is the entire reason it is an enum and not a boolean.
    """


class ReconstructionConfidence(BaseModel):
    """
    The number the confidence gate reads in section 7 step 3. It ships with its own components AND its own weights so that a judge, a test, or the agent can recompute it from the response alone.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    score: float = Field(..., ge=0.0, le=1.0)
    """
    Weighted sum of the components below. Hard floor: a mesh under 100 faces scores 0.0 regardless of components, because there is nothing there to be confident about.
    """
    band: Band
    """
    Coarse bucket for the UI and for the escalation decision. The thresholds are documented guesses in config until Day 3 measures them against three real objects, which is what calibrated reports.
    """
    calibrated: bool
    """
    false until the band thresholds have been measured rather than guessed. Saying so in the payload is cheaper than being asked on camera.
    """
    components: ConfidenceComponents
    weights: ConfidenceWeights


class ReconstructionResult(BaseModel):
    """
    What POST /v1/reconstruct returns on success. There is no status field: either this document comes back with 200, or the caller gets a 4xx/5xx error envelope. Nothing in between. Every number here is measured by the service rather than asserted, and the confidence weights ship inside the payload so the score is recomputable by anyone holding the response.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: SchemaVersion = Field(..., alias="schemaVersion")
    """
    Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.
    """
    request_id: str = Field(..., alias="requestId", pattern="^[a-z0-9][a-z0-9-]{7,63}$")
    """
    Echoed from the request, and the key the mesh object was written under.
    """
    completed_at: AwareDatetime = Field(..., alias="completedAt")
    """
    RFC 3339 timestamp taken on the server after the upload succeeded.
    """
    mesh: ReconstructedMesh
    material: MaterialEstimate
    confidence: ReconstructionConfidence
    pipeline: PipelineInfo
    images: ImageAccounting
    timings: StageTimings
    notices: list[ReconstructionNotice] | None = Field(None, max_length=8)
    """
    Bounded list of things the caller should know about this result - an assumed scale, an uncalibrated confidence, a stub pipeline. Named rules, never library messages.
    """
