/* Step the world, decide what happened, and hash it. */

import type { SceneDescription } from "@rinne/contracts";
import type { SimulationNotice, SimulationResult } from "@rinne/contracts";
import {
  buildScene,
  engineVersion,
  tiltDegrees,
  GROUND_HALF_EXTENT,
  type Quaternion,
} from "./world.js";

/** Pose must move less than this, for this many steps, to count as settled. */
const SETTLE_TRANSLATION_METERS = 0.001;
const SETTLE_TILT_DEGREES = 0.5;
const SETTLE_FRAMES = 60;

/** Up-axis past 45 degrees is tipped; drift past a quarter of the longest edge slid. */
const TIP_DEGREES = 45;
const SLIDE_RATIO = 0.25;

const DIGEST_DECIMALS = 6;
const MAX_NOTICES = 8;
const DEFAULT_PUSH_SECONDS = 0.2;

const NOTICE_TEXT: Record<SimulationNotice["code"], string> = {
  "collider-is-convex-hull":
    "The body is the convex hull of the mesh. Concavities are not simulated.",
  "collider-decimated": "Hull points were thinned to one per voxel so the body can come to rest.",
  "center-of-mass-not-applied":
    "centerOfMass was supplied but the engine derives it from the hull, so it was not applied.",
  "did-not-settle": "The body was still moving at maxSteps, so the verdict is inconclusive.",
  "left-the-ground-plane": "The body travelled beyond the ground plane and then fell freely.",
  "load-test-not-implemented":
    "Load tests are not simulated yet; the body was released and allowed to settle.",
};

const withoutNegativeZero = (value: number): number => (Object.is(value, -0) ? 0 : value);

export function digestOf(parts: readonly (string | number)[]): string {
  const canonical = parts
    .map((part) =>
      typeof part === "number" ? withoutNegativeZero(part).toFixed(DIGEST_DECIMALS) : part,
    )
    .join("|");

  let hash = 0xcbf29ce484222325n;
  const prime = 0x100000001b3n;
  const mask = 0xffffffffffffffffn;
  for (let i = 0; i < canonical.length; i += 1) {
    hash = ((hash ^ BigInt(canonical.charCodeAt(i) & 0xff)) * prime) & mask;
  }
  return hash.toString(16).padStart(16, "0");
}

export interface SimulateOptions {
  readonly runtime: "node" | "browser";
  /** Injectable so a test can assert on a fixed timestamp. */
  readonly now?: () => Date;
}

export function simulateScene(
  scene: SceneDescription,
  points: Float32Array,
  options: SimulateOptions,
): SimulationResult {
  const startedAt = performance.now();
  const built = buildScene(scene, points);
  const { world, body, extent } = built;
  const setupMs = Math.round(performance.now() - startedAt);

  const substeps = scene.solver.substeps ?? 1;
  world.timestep = scene.solver.timestepSeconds / substeps;

  const notices: SimulationNotice[] = [
    {
      code: "collider-is-convex-hull",
      severity: "info",
      message: NOTICE_TEXT["collider-is-convex-hull"],
    },
  ];
  if (built.hullVertices < built.sourceVertices) {
    notices.push({
      code: "collider-decimated",
      severity: "info",
      message: NOTICE_TEXT["collider-decimated"],
    });
  }
  if (scene.body.centerOfMass !== undefined) {
    notices.push({
      code: "center-of-mass-not-applied",
      severity: "warning",
      message: NOTICE_TEXT["center-of-mass-not-applied"],
    });
  }
  if (scene.test.kind === "load") {
    notices.push({
      code: "load-test-not-implemented",
      severity: "warning",
      message: NOTICE_TEXT["load-test-not-implemented"],
    });
  }

  const steppingStarted = performance.now();
  const origin = { ...body.translation() };

  const push = scene.test.kind === "tip" ? tipPush(scene, extent.size.y, origin) : null;
  const pushSteps =
    push === null
      ? 0
      : Math.max(
          1,
          Math.round(
            (scene.test.kind === "tip" ? (scene.test.durationSeconds ?? DEFAULT_PUSH_SECONDS) : 0) /
              scene.solver.timestepSeconds,
          ),
        );

  let steps = 0;
  let calm = 0;
  let settled = false;
  let referenceTranslation = { ...origin };
  let referenceTilt = tiltDegrees(body.rotation());

  try {
    for (; steps < scene.solver.maxSteps; steps += 1) {
      // Added ONCE. Rapier's force accumulator persists across steps, so
      // re-adding each step ramps the push instead of holding it steady.
      if (push !== null && steps === 0) {
        body.addForceAtPoint(push.force, push.point, true);
      } else if (push !== null && steps === pushSteps) {
        body.resetForces(true);
      }

      for (let sub = 0; sub < substeps; sub += 1) world.step();

      const translation = body.translation();
      const tilt = tiltDegrees(body.rotation());
      const moved = Math.hypot(
        translation.x - referenceTranslation.x,
        translation.y - referenceTranslation.y,
        translation.z - referenceTranslation.z,
      );

      if (
        moved < SETTLE_TRANSLATION_METERS &&
        Math.abs(tilt - referenceTilt) < SETTLE_TILT_DEGREES
      ) {
        calm += 1;
      } else {
        calm = 0;
        referenceTranslation = { ...translation };
        referenceTilt = tilt;
      }

      if (calm >= SETTLE_FRAMES && steps >= pushSteps) {
        settled = true;
        steps += 1;
        break;
      }
    }

    const translation = { ...body.translation() };
    const rotation: Quaternion = { ...body.rotation() };
    const tilt = tiltDegrees(rotation);
    const drift = Math.hypot(translation.x - origin.x, translation.z - origin.z);
    const longestEdge = Math.max(extent.size.x, extent.size.y, extent.size.z) || 1;

    let verdict: SimulationResult["outcome"]["verdict"];
    if (!settled) verdict = "inconclusive";
    else if (tilt > TIP_DEGREES) verdict = "tipped";
    else if (drift > longestEdge * SLIDE_RATIO) verdict = "slid";
    else verdict = "stable";

    if (!settled) {
      notices.push({
        code: "did-not-settle",
        severity: "warning",
        message: NOTICE_TEXT["did-not-settle"],
      });
    }
    if (
      Math.abs(translation.x) > GROUND_HALF_EXTENT ||
      Math.abs(translation.z) > GROUND_HALF_EXTENT
    ) {
      notices.push({
        code: "left-the-ground-plane",
        severity: "warning",
        message: NOTICE_TEXT["left-the-ground-plane"],
      });
    }

    const stepMs = Math.round(performance.now() - steppingStarted);
    const clock = options.now ?? ((): Date => new Date());

    return {
      schemaVersion: 1,
      sceneId: scene.sceneId,
      completedAt: clock().toISOString(),
      host: { runtime: options.runtime, engine: "rapier3d-compat", engineVersion: engineVersion() },
      outcome: {
        verdict,
        settled,
        steps,
        simulatedSeconds: round6(steps * scene.solver.timestepSeconds),
        tiltDegrees: round6(tilt),
        driftMeters: round6(drift),
      },
      finalPose: {
        translation: {
          x: round6(translation.x),
          y: round6(translation.y),
          z: round6(translation.z),
        },
        rotation: {
          x: round6(rotation.x),
          y: round6(rotation.y),
          z: round6(rotation.z),
          w: round6(rotation.w),
        },
      },
      collider: {
        kind: "convex-hull",
        sourceVertices: built.sourceVertices,
        hullVertices: built.hullVertices,
        massKilograms: scene.body.massKilograms,
      },
      determinism: {
        seed: scene.solver.seed,
        timestepSeconds: scene.solver.timestepSeconds,
        substeps,
        digest: digestOf([
          scene.sceneId,
          scene.solver.seed,
          scene.solver.timestepSeconds,
          substeps,
          verdict,
          steps,
          translation.x,
          translation.y,
          translation.z,
          rotation.x,
          rotation.y,
          rotation.z,
          rotation.w,
        ]),
      },
      timings: { setupMs, stepMs, totalMs: Math.round(performance.now() - startedAt) },
      // The contract bounds notices at 8 and generates a tuple union, so the
      // slice is what makes this assertion true rather than hopeful.
      notices: notices.slice(0, MAX_NOTICES) as SimulationResult["notices"],
    };
  } finally {
    world.free();
  }
}

const round6 = (value: number): number =>
  Number(withoutNegativeZero(value).toFixed(DIGEST_DECIMALS));

interface Push {
  readonly force: { readonly x: number; readonly y: number; readonly z: number };
  readonly point: { readonly x: number; readonly y: number; readonly z: number };
}

function tipPush(
  scene: SceneDescription,
  height: number,
  origin: { readonly x: number; readonly z: number },
): Push | null {
  if (scene.test.kind !== "tip") return null;
  const theta = scene.test.directionDegrees * (Math.PI / 180);
  const magnitude = scene.test.forceNewtons;
  return {
    force: { x: Math.cos(theta) * magnitude, y: 0, z: Math.sin(theta) * magnitude },
    point: { x: origin.x, y: height * scene.test.pushHeightRatio, z: origin.z },
  };
}
