import type { ReconstructionResult, SceneDescription } from "@rinne/contracts";

/* A ReconstructionResult plus a test kind becomes one contract-valid scene, for
   REPLAY IN THE VIEWER. The agent's own scene is the record of truth; this is a
   viewer concern - provenance.source is "cockpit", not "agent" - and it mirrors
   services/agent/src/rinne_agent/scene.py exactly, so what a person watches is
   what the agent would have simulated. */

const GRAVITY = 9.81;

/* Section 0c measured the tipping boundary at 0.51 of body weight. A force fixed
   in newtons is meaningless across masses, so the push is scaled to the body. */
const TIP_FORCE_RATIO = 0.5;
const TIP_HEIGHT_RATIO = 0.9;
const TIP_DIRECTION_DEGREES = 0;
const TIP_DURATION_SECONDS = 0.2;
const DROP_HEIGHT_METERS = 0.1;
/* A crash is a drop with enough height to matter. Same test kind, same contract,
   same solver - only the potential energy differs, and that is the point. */
const IMPACT_HEIGHT_METERS = 1.5;
const LOAD_MULTIPLE = 2;

const TIMESTEP_SECONDS = 1 / 60;
const MAX_STEPS = 900;
const SEED = 42;
const GROUND_FRICTION = 0.6;
const GROUND_RESTITUTION = 0.1;

export type PreviewKind = "tip" | "drop" | "impact" | "load";

export interface PreviewTest {
  readonly kind: PreviewKind;
  readonly title: string;
  /** What the viewer is actually watching, in one sentence. */
  readonly caption: string;
}

export const PREVIEW_TESTS: readonly PreviewTest[] = [
  {
    kind: "tip",
    title: "Lateral push",
    caption: "A force of half the object's own weight, applied near the top. Does it topple?",
  },
  {
    kind: "drop",
    title: "Drop",
    caption: "Released from 10 cm. Does it land and settle, or keep going?",
  },
  {
    kind: "impact",
    title: "Impact",
    caption: "Dropped from 1.5 m. Where does it strike, and how far does it travel after?",
  },
  {
    kind: "load",
    title: "Load",
    caption: "Twice its own mass placed on the top face.",
  },
];

function round4(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}

function heightFor(kind: PreviewKind): number {
  return kind === "impact" ? IMPACT_HEIGHT_METERS : DROP_HEIGHT_METERS;
}

function testBlock(kind: PreviewKind, result: ReconstructionResult): SceneDescription["test"] {
  const mass = result.material.massKilograms;

  if (kind === "load") {
    const footprint = Math.min(result.mesh.extent.x, result.mesh.extent.z);
    return {
      kind: "load",
      loadKilograms: round4(Math.min(mass * LOAD_MULTIPLE, 2000)),
      contactRadius: round4(Math.max(footprint * 0.25, 0.001)),
    };
  }

  if (kind === "drop" || kind === "impact") {
    return { kind: "drop", dropHeightMeters: heightFor(kind) };
  }

  return {
    kind: "tip",
    pushHeightRatio: TIP_HEIGHT_RATIO,
    forceNewtons: round4(Math.min(mass * GRAVITY * TIP_FORCE_RATIO, 5000)),
    directionDegrees: TIP_DIRECTION_DEGREES,
    durationSeconds: TIP_DURATION_SECONDS,
  };
}

export function buildPreviewScene(
  result: ReconstructionResult,
  kind: PreviewKind,
): SceneDescription {
  // Normalisation already seats the mesh at y=0, so only a fall starts above it.
  const resting = kind === "drop" || kind === "impact" ? heightFor(kind) : 0;

  return {
    schemaVersion: 1,
    sceneId: result.requestId,
    units: { length: "m", mass: "kg" },
    gravity: { x: 0, y: -GRAVITY, z: 0 },
    ground: { friction: GROUND_FRICTION, restitution: GROUND_RESTITUTION },
    body: {
      mesh: result.mesh.sha256
        ? { uri: result.mesh.uri, format: "glb", sha256: result.mesh.sha256 }
        : { uri: result.mesh.uri, format: "glb" },
      massKilograms: result.material.massKilograms,
      friction: result.material.friction,
      restitution: result.material.restitution,
      initialTranslation: { x: 0, y: resting, z: 0 },
    },
    test: testBlock(kind, result),
    solver: { timestepSeconds: TIMESTEP_SECONDS, maxSteps: MAX_STEPS, seed: SEED },
    provenance: {
      source: "cockpit",
      estimatedBy: result.pipeline.name,
      reconstructionConfidence: result.confidence.score,
      materialConfidence: result.material.confidence,
    },
  };
}
