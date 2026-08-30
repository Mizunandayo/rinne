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


class JobState(StrEnum):
    """
    The exhaustive state set from section 7. skipped_low_risk is a LEGITIMATE terminal outcome and the most common one - triage deciding no review is needed is the product working, not failing. gated is designed and NOT shipped: the Gemma tier-0 gate was cut on Aug 28, so nothing in this build emits it; it stays in the enum so the three-tier cascade remains describable and the cut remains visible. failed is reachable from every non-terminal state and carries error and lastGoodState.
    """

    queued = "queued"
    gated = "gated"
    skipped_low_risk = "skipped_low_risk"
    triaged = "triaged"
    simulating = "simulating"
    awaiting_verification = "awaiting_verification"
    refitting = "refitting"
    reporting = "reporting"
    done = "done"
    failed = "failed"


class ContentType(StrEnum):
    """
    Allowlisted before the object is read. The same three types the reconstruction service accepts, so a scan that triages cannot then be refused downstream.
    """

    image_jpeg = "image/jpeg"
    image_png = "image/png"
    image_webp = "image/webp"


class ScanSource(BaseModel):
    """
    The object that triggered this job, as reported by the storage event. Recorded in full so the decision log is reproducible from the document alone - a judge can re-run the exact object the agent saw.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    bucket: str = Field(..., pattern="^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")
    """
    Checked against one configured bucket before any work happens. The delivery is authenticated by IAM, but the bucket name inside it is still payload.
    """
    object: str = Field(..., max_length=512, min_length=1)
    generation: str = Field(..., pattern="^[0-9]{1,20}$")
    """
    GCS reports generation as a decimal string, and it stays a string here for the same reason: it is an int64 identifier, not a number anything does arithmetic on. It is part of the jobId derivation, so overwriting an object produces a new job rather than silently reusing the old one.
    """
    content_type: ContentType = Field(..., alias="contentType")
    """
    Allowlisted before the object is read. The same three types the reconstruction service accepts, so a scan that triages cannot then be refused downstream.
    """
    size_bytes: int = Field(..., alias="sizeBytes", ge=1, le=26214400)
    received_at: AwareDatetime = Field(..., alias="receivedAt")
    event_id: str | None = Field(None, alias="eventId", max_length=128)
    """
    CloudEvent id of the delivery that created the job. Two deliveries of one object carry the same id; a genuine re-upload does not. Evidence, not a control - the control is the create-only write.
    """


class Shape(StrEnum):
    """
    What the model saw. no-object is the case the cut Gemma tier-0 gate would have caught more cheaply; Flash catches it now, which is the cost argument for that gate written down as a value rather than as prose.
    """

    tall_narrow = "tall-narrow"
    flat_wide = "flat-wide"
    stack = "stack"
    irregular = "irregular"
    no_object = "no-object"


class Basis(StrEnum):
    flash_triage_v1 = "flash-triage-v1"


class TriageRecord(BaseModel):
    """
    Section 7 step 1. The judgment a script cannot make: is this object worth a physics review at all. shape is the classification the decision rested on, and it is the input Day 5's test selection reads - recording it here means selection does not have to look at the image a second time.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    review: bool
    """
    true: this warrants a physics review, and the job moves to triaged. false: it does not, and the job terminates in skipped_low_risk.
    """
    shape: Shape
    """
    What the model saw. no-object is the case the cut Gemma tier-0 gate would have caught more cheaply; Flash catches it now, which is the cost argument for that gate written down as a value rather than as prose.
    """
    confidence: float = Field(..., ge=0.0, le=1.0)
    """
    The model's own stated confidence in this triage call. NOT the reconstruction confidence and NOT the gate input - it is here so a wrong triage can be told apart from an unsure one.
    """
    rationale: str = Field(..., max_length=280, min_length=1)
    model: str = Field(..., max_length=64, min_length=1)
    """
    Exact model id that produced this, so the log says which tier answered.
    """
    basis: Basis
    latency_ms: int = Field(..., alias="latencyMs", ge=0, le=600000)
    prompt_tokens: int | None = Field(None, alias="promptTokens", ge=0, le=10000000)
    response_tokens: int | None = Field(None, alias="responseTokens", ge=0, le=10000000)


class JobActor(StrEnum):
    """
    Which step of the loop acted. Closed so the dashboard can group by it, and so a step that does not exist yet cannot appear in a log without a schema change.
    """

    ingest = "ingest"
    triage = "triage"
    gate = "gate"
    reconstruction = "reconstruction"
    physics = "physics"
    refit = "refit"
    report = "report"
    operator = "operator"


class TestKind(StrEnum):
    """
    Which physics test the agent selected. Mirrors the oneOf kinds in scene-description.schema.json; none is what a shape that cannot be tested gets.
    """

    tip = "tip"
    load = "load"
    drop = "drop"
    none = "none"


class Basis1(StrEnum):
    flash_selection_v1 = "flash-selection-v1"


class SelectionRecord(BaseModel):
    """
    Section 7 step 2. Different objects genuinely receive different tool calls, and this is where that shows in the log. The model chooses from a closed set; it does not invent a test.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: TestKind
    rationale: str = Field(..., max_length=280, min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    model: str = Field(..., max_length=64, min_length=1)
    basis: Basis1
    latency_ms: int = Field(..., alias="latencyMs", ge=0, le=600000)
    prompt_tokens: int | None = Field(None, alias="promptTokens", ge=0, le=10000000)
    response_tokens: int | None = Field(None, alias="responseTokens", ge=0, le=10000000)


class Band(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class Material(StrEnum):
    cardboard = "cardboard"
    wood = "wood"
    plastic = "plastic"
    metal = "metal"
    glass = "glass"
    fabric = "fabric"
    unknown = "unknown"


class ReconstructionRecord(BaseModel):
    """
    What POST /v1/reconstruct returned, reduced to the fields the gate and the cockpit read. The full ReconstructionResult is not copied here - the mesh URI is the pointer to everything else.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: str = Field(..., alias="requestId", pattern="^[a-z0-9][a-z0-9-]{7,63}$")
    mesh_uri: str = Field(
        ...,
        alias="meshUri",
        pattern="^gs://[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]/.{1,512}$",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    band: Band
    calibrated: bool
    material: Material
    material_confidence: float = Field(..., alias="materialConfidence", ge=0.0, le=1.0)
    mass_kilograms: float | None = Field(None, alias="massKilograms", gt=0.0, le=5000.0)
    face_count: int | None = Field(None, alias="faceCount", ge=0, le=10000000)
    watertight: bool | None = None
    pipeline: str | None = Field(None, max_length=64, min_length=1)
    latency_ms: int = Field(..., alias="latencyMs", ge=0, le=600000)


class Verdict(StrEnum):
    stable = "stable"
    tipped = "tipped"
    slid = "slid"
    inconclusive = "inconclusive"


class NoticeCode(StrEnum):
    """
    One advisory the physics service attached to a result. These are not failures; they are the caveats a viewer has to see before believing a verdict.
    """

    collider_is_convex_hull = "collider-is-convex-hull"
    collider_decimated = "collider-decimated"
    center_of_mass_not_applied = "center-of-mass-not-applied"
    did_not_settle = "did-not-settle"
    left_the_ground_plane = "left-the-ground-plane"
    load_test_not_implemented = "load-test-not-implemented"


class Name(StrEnum):
    reconstruction_confidence = "reconstruction-confidence"
    material_confidence = "material-confidence"
    physics_verdict = "physics-verdict"


class GateInput(BaseModel):
    """
    One measured value the policy compared against one threshold. physics-verdict is 0.0 when the engine answered inconclusive and 1.0 otherwise, so every input renders the same way.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Name
    value: float = Field(..., ge=0.0, le=1.0)
    threshold: float = Field(..., ge=0.0, le=1.0)
    passed: bool


class GateReason(StrEnum):
    """
    Why the gate refused. A closed set so the cockpit can branch on it. physics-test-unsupported is the load test: the engine accepts the scene, applies no force, and settles to a stable that means nothing - so the agent asks a human rather than reporting it.
    """

    low_reconstruction_confidence = "low-reconstruction-confidence"
    low_material_confidence = "low-material-confidence"
    physics_inconclusive = "physics-inconclusive"
    physics_test_unsupported = "physics-test-unsupported"


class Policy(StrEnum):
    """
    The rule's name and version. A threshold change keeps the name; a change to WHAT is compared bumps it.
    """

    min_confidence_v1 = "min-confidence-v1"


class Decision(StrEnum):
    report = "report"
    escalate = "escalate"


class GateRecord(BaseModel):
    """
    THE DECLARED POLICY, section 7 step 3. Never a bare if: the record names the rule, the threshold it used, every input it compared, and whether those thresholds were ever measured. That is what makes a refusal auditable and the threshold configurable without a code change.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    policy: Policy
    """
    The rule's name and version. A threshold change keeps the name; a change to WHAT is compared bumps it.
    """
    threshold: float = Field(..., ge=0.0, le=1.0)
    observed: float = Field(..., ge=0.0, le=1.0)
    """
    The binding input - the lowest value the policy saw. This is the number that decided it.
    """
    calibrated: bool
    """
    Whether the thresholds were measured against real objects or are still documented guesses. Reported either way; it does not change the decision.
    """
    decision: Decision
    inputs: list[GateInput] = Field(..., max_length=6)
    reasons: list[GateReason] | None = Field(None, max_length=6)
    at: AwareDatetime


class JobError(BaseModel):
    """
    Why the job failed. rule is a named rule from a closed set of sentences this service owns - never a library message, never a stack trace, never a caller's bytes. Same discipline as the reconstruction service's notices.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    rule: str = Field(..., max_length=200, min_length=1)
    at: AwareDatetime
    retryable: bool
    """
    Whether another delivery could plausibly succeed. A retryable failure is why the transport is allowed to redeliver; a non-retryable one is why the handler acknowledges a message it will never process rather than letting Pub/Sub redeliver it for a week.
    """
    actor: JobActor | None = None


class DecisionEntry(BaseModel):
    """
    One line of the decision log: what changed the state, when, and why. The model and the confidence are repeated here as well as on the record they came from, because the trail has to read top to bottom on camera without expanding anything.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    at: AwareDatetime
    state: JobState
    actor: JobActor
    summary: str = Field(..., max_length=240, min_length=1)
    model: str | None = Field(None, max_length=64)
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    latency_ms: int | None = Field(None, alias="latencyMs", ge=0, le=600000)


class SimulationRecord(BaseModel):
    """
    What POST /v1/simulate returned. inconclusive is the engine refusing to guess rather than an error, and the gate treats it as a first-class reason to ask a human.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    scene_id: str = Field(..., alias="sceneId", pattern="^[a-z0-9][a-z0-9-]{7,63}$")
    verdict: Verdict
    settled: bool
    steps: int = Field(..., ge=0, le=20000)
    tilt_degrees: float = Field(..., alias="tiltDegrees", ge=0.0, le=180.0)
    drift_meters: float = Field(..., alias="driftMeters", ge=0.0, le=100000.0)
    digest: str = Field(..., pattern="^[a-f0-9]{16}$")
    hull_vertices: int | None = Field(None, alias="hullVertices", ge=0, le=100000)
    latency_ms: int = Field(..., alias="latencyMs", ge=0, le=600000)
    notices: list[NoticeCode] | None = Field(None, max_length=8)
    """
    Notice codes the physics service attached. load-test-not-implemented is the one the gate acts on: an unsupported test settles untouched and reports a meaningless stable.
    """


class AgentJob(BaseModel):
    """
    One scan, one Firestore document, one exhaustive state machine. This is the decision log section 7 promises, and the only place a job's state lives - there is no in-process table it could disagree with. It is a shared contract rather than a private shape because the cockpit reads it from TypeScript, and because generating the ten states into both languages is what turns "no implicit states" into a build gate instead of a discipline.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: SchemaVersion = Field(..., alias="schemaVersion")
    """
    Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.
    """
    job_id: str = Field(..., alias="jobId", pattern="^[a-z0-9][a-z0-9-]{7,63}$")
    """
    Firestore document key, and later the reconstruction requestId and the sceneId. Derived deterministically from bucket, object and generation so a redelivered event maps to the same document instead of a second job. Same pattern as requestId and sceneId, for the same reason: no slash, no dot, no traversal.
    """
    state: JobState
    last_good_state: JobState | None = Field(None, alias="lastGoodState")
    attempts: int = Field(..., ge=0, le=6)
    """
    How many times the agent has begun work on this job. Section 12 forbids unbounded loops; this is where that rule is enforced for the agent path, and the ceiling of 6 matches the tool-loop cap and SceneDescription.provenance.refitIteration.
    """
    created_at: AwareDatetime = Field(..., alias="createdAt")
    """
    RFC 3339 timestamp of the delivery that created this document.
    """
    updated_at: AwareDatetime = Field(..., alias="updatedAt")
    """
    RFC 3339 timestamp of the last accepted transition.
    """
    source: ScanSource
    triage: TriageRecord | None = None
    error: JobError | None = None
    selection: SelectionRecord | None = None
    reconstruction: ReconstructionRecord | None = None
    simulation: SimulationRecord | None = None
    gate: GateRecord | None = None
    decisions: list[DecisionEntry] = Field(..., max_length=24)
    """
    Append-only audit trail. Bounded so a redelivery storm or a buggy loop cannot inflate a document, and because Firestore charges by document size.
    """
