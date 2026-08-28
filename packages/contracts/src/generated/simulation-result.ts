/* eslint-disable */
/**
 * GENERATED FILE — DO NOT EDIT BY HAND.
 *
 * Source of truth : packages/contracts/schemas
 * Regenerate      : pnpm --filter @rinne/contracts run generate:ts
 *
 * CI runs the same generator with --check and fails the build if this file
 * differs. A schema edit without a regeneration is a build failure, which is
 * the entire point of defining the contract once.
 */

/**
 * What one SceneDescription produced when it was simulated. The same scene document handed to the browser build and to the headless Node build must produce the same determinism.digest; that equality is the shared-engine claim, and parity.test.ts asserts it. Nothing host-specific belongs in this file except the host block itself, which exists precisely so a reader can tell which side produced the document.
 */
export interface SimulationResult {
  /**
   * Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.
   */
  schemaVersion: 1;
  /**
   * Echoed from the SceneDescription that produced this result.
   */
  sceneId: string;
  /**
   * RFC 3339 timestamp taken after the last step. Deliberately NOT part of the determinism digest - a wall clock is the one thing two hosts can never agree on.
   */
  completedAt: string;
  host: SimulationHost;
  outcome: SimulationOutcome;
  finalPose: BodyPose;
  collider: ColliderSummary;
  determinism: DeterminismRecord;
  timings: SimulationTimings;
  /**
   * Bounded list of things the caller should know about this result - an unsettled body, a centre of mass that could not be applied, a decimated collider. Named rules, never library messages.
   *
   * @maxItems 8
   */
  notices?:
    | []
    | [SimulationNotice]
    | [SimulationNotice, SimulationNotice]
    | [SimulationNotice, SimulationNotice, SimulationNotice]
    | [SimulationNotice, SimulationNotice, SimulationNotice, SimulationNotice]
    | [SimulationNotice, SimulationNotice, SimulationNotice, SimulationNotice, SimulationNotice]
    | [
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
      ]
    | [
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
      ]
    | [
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
        SimulationNotice,
      ];
}
/**
 * Which side ran it. This is the only field that is allowed to differ between two runs of the same scene, and it exists so that a parity comparison can say which two things it compared.
 */
export interface SimulationHost {
  runtime: "node" | "browser";
  engine: "rapier3d-compat";
  engineVersion: string;
}
/**
 * The answer, plus the two measurements it was derived from. verdict is a closed enum so the agent can branch on it; tiltDegrees and driftMeters are reported so a human can see why it said that.
 */
export interface SimulationOutcome {
  /**
   * stable: settled within tolerance of where it started. tipped: settled with its up-axis more than 45 degrees from vertical. slid: settled upright but displaced more than a quarter of its longest edge. inconclusive: never settled inside solver.maxSteps, which is a real answer about the scene and not an error.
   */
  verdict: "stable" | "tipped" | "slid" | "inconclusive";
  /**
   * True when the pose stopped changing for a full settle window. Deliberately not a velocity test: a convex hull resting on a plane keeps a small non-zero angular velocity indefinitely without moving.
   */
  settled: boolean;
  steps: number;
  simulatedSeconds: number;
  /**
   * Angle between the body's local +Y after simulation and world +Y. Yaw does not count as tilt, which is why this is measured from the up-axis rather than from the quaternion's angle.
   */
  tiltDegrees: number;
  /**
   * Horizontal distance from the initial translation. Vertical motion is excluded: a body settling onto the ground moves down, and that is not drift.
   */
  driftMeters: number;
}
export interface BodyPose {
  translation: PoseVector;
  rotation: PoseRotation;
}
/**
 * Metres. Not named vec3: every definitions key becomes a flat top-level TypeScript identifier and scene-description.schema.json already owns that name.
 */
export interface PoseVector {
  x: number;
  y: number;
  z: number;
}
/**
 * Unit quaternion, Rapier's own component order.
 */
export interface PoseRotation {
  x: number;
  y: number;
  z: number;
  w: number;
}
/**
 * What the mesh actually became. A reconstruction is not convex and this says so in the payload rather than in a comment.
 */
export interface ColliderSummary {
  kind: "convex-hull";
  sourceVertices: number;
  /**
   * After voxel decimation. A hull built from every reconstruction vertex has hundreds of near-coplanar faces, its contact manifold flickers every step, and the body then never comes to rest - so decimation is a correctness requirement, not an optimisation.
   */
  hullVertices: number;
  massKilograms: number;
}
/**
 * Everything needed to reproduce this run, plus the digest that makes two runs comparable in one string. The digest covers the scene id, the solver settings, the verdict, the step count and the final pose at 6dp. It excludes completedAt and the host block by design.
 */
export interface DeterminismRecord {
  seed: number;
  timestepSeconds: number;
  substeps: number;
  /**
   * FNV-1a 64 over the canonical form, as 16 lowercase hex characters. Not a cryptographic hash and not a security control: it is a comparison key that has to compute identically and synchronously in Node and in a browser, which rules out both node:crypto and the async crypto.subtle.
   */
  digest: string;
}
/**
 * Wall-clock milliseconds. Not named stageTimings: reconstruction-result.schema.json already owns that name.
 */
export interface SimulationTimings {
  setupMs: number;
  stepMs: number;
  totalMs: number;
}
/**
 * One caveat about this result. The code is a closed enum so a consumer can branch on it; the message is a fixed sentence for a human.
 */
export interface SimulationNotice {
  code:
    | "collider-is-convex-hull"
    | "collider-decimated"
    | "center-of-mass-not-applied"
    | "did-not-settle"
    | "left-the-ground-plane"
    | "load-test-not-implemented";
  severity: "info" | "warning";
  message: string;
}
