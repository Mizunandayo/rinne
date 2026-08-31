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
 * What POST /v1/reconstruct returns on success. There is no status field: either this document comes back with 200, or the caller gets a 4xx/5xx error envelope. Nothing in between. Every number here is measured by the service rather than asserted, and the confidence weights ship inside the payload so the score is recomputable by anyone holding the response.
 */
export interface ReconstructionResult {
  /**
   * Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.
   */
  schemaVersion: 1;
  /**
   * Echoed from the request, and the key the mesh object was written under.
   */
  requestId: string;
  /**
   * RFC 3339 timestamp taken on the server after the upload succeeded.
   */
  completedAt: string;
  mesh: ReconstructedMesh;
  material: MaterialEstimate;
  confidence: ReconstructionConfidence;
  pipeline: PipelineInfo;
  images: ImageAccounting;
  timings: StageTimings;
  /**
   * Bounded list of things the caller should know about this result - an assumed scale, an uncalibrated confidence, a stub pipeline. Named rules, never library messages.
   *
   * @maxItems 8
   */
  notices?:
    | []
    | [ReconstructionNotice]
    | [ReconstructionNotice, ReconstructionNotice]
    | [ReconstructionNotice, ReconstructionNotice, ReconstructionNotice]
    | [ReconstructionNotice, ReconstructionNotice, ReconstructionNotice, ReconstructionNotice]
    | [
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
      ]
    | [
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
      ]
    | [
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
      ]
    | [
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
        ReconstructionNotice,
      ];
}
/**
 * The stored artifact plus the measurements taken from it. The physics service and the agent both read these, so they live in the contract rather than being recomputed twice and disagreeing.
 */
export interface ReconstructedMesh {
  /**
   * gs:// ONLY, matching the meshRef precedent in scene-description.schema.json. The physics service fetches this URI and this document is shaped by model output, so an unrestricted scheme here is a server-side request forgery primitive pointed at the metadata server. Restricting the scheme at the contract boundary kills that class of attack once, rather than in every handler that might forget.
   */
  uri: string;
  format: "glb";
  /**
   * Integrity check on the stored asset, computed over the exact bytes uploaded.
   */
  sha256?: string;
  /**
   * Size of the stored GLB, so a viewer can budget its fetch before starting it.
   */
  byteLength: number;
  vertexCount: number;
  faceCount: number;
  /**
   * Reported by trimesh AFTER normalisation. Marching cubes routinely produces duplicate vertices and degenerate faces, either of which makes a genuinely closed surface report false, so this is measured post-merge or it is meaningless.
   */
  watertight: boolean;
  extent: MeshExtent;
  /**
   * Signed volume magnitude of the normalised mesh. Feeds volumePlausibility and the mass estimate.
   */
  volumeCubicMeters: number;
  /**
   * Y, always. Marching cubes emits Z-up; normalisation rotates it once here so no consumer has to guess.
   */
  upAxis: "y";
  /**
   * assumed: scale came from assumedLongestDimensionMeters and is a guess. measured: scale came from a fiducial marker of known size. Day 7 flips this value with no contract change, which is the entire reason it is an enum and not a boolean.
   */
  scaleBasis: "assumed" | "measured";
}
/**
 * Axis-aligned bounding box dimensions in metres, after normalisation. Not named vec3: every definitions key becomes a flat top-level TypeScript identifier and scene-description.schema.json already owns that name.
 */
export interface MeshExtent {
  x: number;
  y: number;
  z: number;
}
/**
 * The physical properties the physics service needs, plus how confident the service is that they are right. The confidences are low on purpose: a weak material signal SHOULD push a borderline job into escalation rather than quietly through it.
 */
export interface MaterialEstimate {
  name: "cardboard" | "wood" | "plastic" | "metal" | "glass" | "fabric" | "unknown";
  /**
   * How the guess was made. heuristic-v1 is the mean-vertex-colour HSV classifier. flash-vision-v1 is the Gemini Flash call that replaces it on Day 4 - it is in the enum now so that swap is a config change rather than a contract change.
   */
  basis: "heuristic-v1" | "flash-vision-v1";
  confidence: number;
  densityKilogramsPerCubicMeter: number;
  /**
   * density * max(volume * solidFraction, 1e-6), capped at 5000 and floored at 1e-4. The bounds match rigidBody.massKilograms so a result drops straight into a SceneDescription.
   */
  massKilograms: number;
  friction: number;
  restitution: number;
}
/**
 * The number the confidence gate reads in section 7 step 3. It ships with its own components AND its own weights so that a judge, a test, or the agent can recompute it from the response alone.
 */
export interface ReconstructionConfidence {
  /**
   * Weighted sum of the components below. Hard floor: a mesh under 100 faces scores 0.0 regardless of components, because there is nothing there to be confident about.
   */
  score: number;
  /**
   * Coarse bucket for the UI and for the escalation decision. The thresholds are documented guesses in config until Day 3 measures them against three real objects, which is what calibrated reports.
   */
  band: "low" | "medium" | "high";
  /**
   * false until the band thresholds have been measured rather than guessed. Saying so in the payload is cheaper than being asked on camera.
   */
  calibrated: boolean;
  components: ConfidenceComponents;
  weights: ConfidenceWeights;
}
/**
 * Each component is measured, in [0,1], and rounded to 4dp so tests are deterministic. foregroundQuality is OPTIONAL because it derives from the segmentation mask, which ships with TripoSR; a build without segmentation omits the key entirely rather than inventing a value for it.
 */
export interface ConfidenceComponents {
  /**
   * How far the density field sat from the iso-surface, sampled one voxel in 64 by the marching-cubes shim. A field that hovers near the threshold everywhere produced a surface that could have gone either way.
   */
  fieldDecisiveness: number;
  /**
   * 1.0 for a closed surface, otherwise scaled by the share of boundary edges - rows of edges_sorted appearing exactly once.
   */
  watertightness: number;
  /**
   * Occupancy of the bounding box, through a triangular window peaking at 0.5 and reaching zero at 0.03 and 1.0. Catches both the wisp and the solid block.
   */
  volumePlausibility: number;
  /**
   * framing * cropping, from the segmentation mask. Absent until segmentation ships, at which point the weights below regain their fourth entry.
   */
  foregroundQuality?: number;
}
/**
 * The exact weights used for THIS response. They sum to 1.0, and they change when a component is added or removed - which is precisely why they are transmitted rather than documented. Same optionality as the components: no foregroundQuality weight without a foregroundQuality component.
 */
export interface ConfidenceWeights {
  fieldDecisiveness: number;
  watertightness: number;
  volumePlausibility: number;
  foregroundQuality?: number;
}
/**
 * Which reconstructor actually ran. This exists so a placeholder can say it is a placeholder, in the payload, without anybody having to remember to mention it.
 */
export interface PipelineInfo {
  /**
   * stub: a deterministic procedural mesh, honest about being one. triposr: single-image feed-forward, fast and coarse. instantmesh: multi-view diffusion into a sparse-view reconstruction, slower and far cleaner. Which one ran is a property of the result, not of the deployment, because the document has to stay readable long after the environment changed.
   */
  name: "stub" | "triposr" | "instantmesh";
  /**
   * Pipeline build identifier. For triposr this is the pinned upstream commit SHA, which is what makes vendoring at a known state a truthful claim rather than a hope.
   */
  version: string;
  device: "cpu" | "cuda";
  /**
   * Determinism seed, when the pipeline takes one. Same role as SceneDescription.solver.seed.
   */
  seed?: number;
}
/**
 * What happened to the uploaded images. reencoded is the visible proof of validation layer 7: the model never saw a byte the client sent, which is what strips EXIF GPS and kills polyglot payloads.
 */
export interface ImageAccounting {
  received: number;
  accepted: number;
  /**
   * How many accepted images the pipeline actually consumed. Day 2 accepts up to four and uses the first; that narrowing is behaviour inside an unchanged contract, and this field is where it is admitted.
   */
  used: number;
  reencoded: boolean;
  /**
   * Longest edge of the re-encoded image handed to the pipeline, after the bound in max_image_edge.
   */
  longestEdgePixels: number;
}
/**
 * Wall-clock milliseconds per stage. Read on camera, and the cheapest way to see a cold GPU start for what it is.
 */
export interface StageTimings {
  validationMs: number;
  inferenceMs: number;
  meshMs: number;
  uploadMs: number;
  totalMs: number;
}
/**
 * One caveat about this result. The code is a closed enum so a consumer can branch on it; the message is for a human and is a fixed sentence, never a library string, a filename, or a byte range.
 */
export interface ReconstructionNotice {
  code:
    | "stub-pipeline"
    | "scale-assumed"
    | "confidence-uncalibrated"
    | "foreground-quality-unavailable"
    | "images-ignored"
    | "material-weak-signal"
    | "low-face-count"
    | "mesh-not-watertight";
  severity: "info" | "warning";
  message: string;
}
