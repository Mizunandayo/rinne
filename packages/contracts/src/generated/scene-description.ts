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
 * Portable, engine-agnostic physics scene. This is the single interchange format between the browser Rapier build, the headless Node Rapier build, and the Python agent, and it is also the exportable simulation artifact. Two hosts given the same document must produce the same result; anything that would let them diverge does not belong in this file.
 */
export interface SceneDescription {
  /**
   * Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.
   */
  schemaVersion: 1;
  /**
   * Stable identifier, also used as the Firestore document key.
   */
  sceneId: string;
  /**
   * Declared explicitly so a unit mismatch is a validation error rather than a physics result that is wrong by a factor of a thousand.
   */
  units: {
    length: "m";
    mass: "kg";
  };
  gravity: Vec3;
  ground: {
    friction: number;
    restitution: number;
  };
  body: RigidBody;
  /**
   * Which physics test the agent selected. Exactly one, chosen per §7 step 2.
   */
  test: TipTest | LoadTest | DropTest;
  solver: {
    timestepSeconds: number;
    /**
     * Hard upper bound on simulation steps. §12 forbids unbounded loops, and this is where that rule is enforced for the physics path — the schema makes an unbounded simulation unrepresentable.
     */
    maxSteps: number;
    substeps?: number;
    /**
     * Determinism seed. Both hosts must use it, or the shared-engine claim is unverifiable.
     */
    seed: number;
  };
  /**
   * Where the estimates in this document came from. Read by the confidence gate in §7 step 3.
   */
  provenance?: {
    source: "agent" | "cockpit" | "refit" | "fixture";
    estimatedBy?: string;
    reconstructionConfidence?: number;
    materialConfidence?: number;
    refitIteration?: number;
  };
}
export interface Vec3 {
  x: number;
  y: number;
  z: number;
}
export interface RigidBody {
  mesh: MeshRef;
  massKilograms: number;
  centerOfMass?: Vec3;
  friction: number;
  restitution: number;
  linearDamping?: number;
  angularDamping?: number;
  initialTranslation: Vec3;
  initialRotationDegrees?: Vec3;
}
export interface MeshRef {
  /**
   * gs:// ONLY. The physics service fetches this URI, and this document is shaped by model output, so an unrestricted scheme here is a server-side request forgery primitive pointed at the metadata server. Restricting the scheme in the schema kills that class of attack at the contract boundary rather than in a handler someone might forget to write.
   */
  uri: string;
  format: "glb";
  /**
   * Integrity check on the fetched asset. Optional on Day 3, required once the cockpit and the agent fetch the same mesh.
   */
  sha256?: string;
}
export interface TipTest {
  kind: "tip";
  /**
   * Height of the applied push as a fraction of the object's total height.
   */
  pushHeightRatio: number;
  forceNewtons: number;
  directionDegrees: number;
  durationSeconds?: number;
}
export interface LoadTest {
  kind: "load";
  loadKilograms: number;
  contactRadius: number;
  offsetFromCenter?: Vec3;
}
export interface DropTest {
  kind: "drop";
  dropHeightMeters: number;
  initialRotationDegrees?: Vec3;
}
