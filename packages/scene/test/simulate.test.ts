import { beforeAll, describe, expect, it } from "vitest";
import type { SceneDescription } from "@rinne/contracts";
import { readPositions } from "../src/glb.js";
import {
  decimate,
  extentOf,
  initScene,
  quaternionFromEulerDegrees,
  tiltDegrees,
} from "../src/world.js";
import { digestOf, simulateScene } from "../src/simulate.js";
import { boxGlb } from "./fixture.js";

const FIXED_CLOCK = (): Date => new Date("2026-08-28T04:00:00.000Z");

function scene(overrides: Partial<SceneDescription> = {}): SceneDescription {
  return {
    schemaVersion: 1,
    sceneId: "scene-000001",
    units: { length: "m", mass: "kg" },
    gravity: { x: 0, y: -9.81, z: 0 },
    ground: { friction: 0.6, restitution: 0.1 },
    body: {
      mesh: { uri: "gs://rinne-artifacts-rinnehackathon/meshes/scene-000001.glb", format: "glb" },
      massKilograms: 2.4,
      friction: 0.55,
      restitution: 0.05,
      initialTranslation: { x: 0, y: 0.02, z: 0 },
    },
    test: {
      kind: "tip",
      pushHeightRatio: 0.9,
      forceNewtons: 6,
      directionDegrees: 0,
      durationSeconds: 0.2,
    },
    solver: { timestepSeconds: 1 / 60, maxSteps: 900, substeps: 4, seed: 42 },
    ...overrides,
  };
}

describe("scene geometry", () => {
  const points = readPositions(boxGlb());

  it("decimation loses no extent, which is why the hull is still the right size", () => {
    const full = extentOf(points);
    const thinned = extentOf(decimate(points));
    expect(thinned.size.x).toBeCloseTo(full.size.x, 6);
    expect(thinned.size.y).toBeCloseTo(full.size.y, 6);
    expect(thinned.size.z).toBeCloseTo(full.size.z, 6);
  });

  it("decimation removes the near-coplanar points that stop a hull settling", () => {
    expect(decimate(points).length).toBeLessThan(points.length);
  });

  it("decimation is order-stable, so parity cannot drift on point order", () => {
    expect([...decimate(points)]).toEqual([...decimate(points)]);
  });

  it("tilt is measured from the up-axis, so yaw is not a tip", () => {
    expect(tiltDegrees({ x: 0, y: 0, z: 0, w: 1 })).toBeCloseTo(0, 6);
    expect(tiltDegrees(quaternionFromEulerDegrees({ x: 0, y: 90, z: 0 }))).toBeCloseTo(0, 6);
    expect(tiltDegrees(quaternionFromEulerDegrees({ x: 0, y: 0, z: 45 }))).toBeCloseTo(45, 4);
    expect(tiltDegrees(quaternionFromEulerDegrees({ x: 90, y: 0, z: 0 }))).toBeCloseTo(90, 4);
  });
});

describe("digest", () => {
  it("treats negative zero as zero", () => {
    expect(digestOf(["a", -0])).toBe(digestOf(["a", 0]));
  });

  it("is sixteen lowercase hex characters", () => {
    expect(digestOf(["scene-000001", 42, 1.5])).toMatch(/^[a-f0-9]{16}$/);
  });

  it("changes when any part changes", () => {
    expect(digestOf(["a", 1])).not.toBe(digestOf(["a", 2]));
  });
});

describe("simulateScene", () => {
  const points = readPositions(boxGlb());
  beforeAll(async () => {
    await initScene();
  });

  it("holds a 2.4kg box against a 6N push", () => {
    const result = simulateScene(scene(), points, { runtime: "node", now: FIXED_CLOCK });
    expect(result.outcome.verdict).toBe("stable");
    expect(result.outcome.settled).toBe(true);
    expect(result.outcome.tiltDegrees).toBeLessThan(5);
  });

  it("tips the same box when the push is large enough", () => {
    const result = simulateScene(
      scene({
        test: {
          kind: "tip",
          pushHeightRatio: 0.9,
          forceNewtons: 18,
          directionDegrees: 0,
          durationSeconds: 0.2,
        },
      }),
      points,
      { runtime: "node", now: FIXED_CLOCK },
    );
    expect(result.outcome.verdict).toBe("tipped");
    expect(result.outcome.tiltDegrees).toBeGreaterThan(45);
  });

  it("settles a dropped box on the ground plane", () => {
    const result = simulateScene(
      scene({
        body: { ...scene().body, initialTranslation: { x: 0, y: 0.4, z: 0 } },
        test: { kind: "drop", dropHeightMeters: 0.4 },
      }),
      points,
      { runtime: "node", now: FIXED_CLOCK },
    );
    expect(result.outcome.settled).toBe(true);
    expect(result.finalPose.translation.y).toBeGreaterThan(-0.05);
    expect(result.finalPose.translation.y).toBeLessThan(0.05);
  });

  it("reports inconclusive rather than inventing a verdict when it never settles", () => {
    // A real answer about the scene, not an error: maxSteps is the §12 bound.
    const result = simulateScene(
      scene({ solver: { timestepSeconds: 1 / 60, maxSteps: 20, substeps: 1, seed: 42 } }),
      points,
      { runtime: "node", now: FIXED_CLOCK },
    );
    expect(result.outcome.verdict).toBe("inconclusive");
    expect(result.outcome.settled).toBe(false);
    expect(result.notices.map((notice) => notice.code)).toContain("did-not-settle");
  });

  it("admits in the payload that the collider is a hull and was thinned", () => {
    const result = simulateScene(scene(), points, { runtime: "node", now: FIXED_CLOCK });
    const codes = result.notices.map((notice) => notice.code);
    expect(result.collider.kind).toBe("convex-hull");
    expect(result.collider.hullVertices).toBeLessThan(result.collider.sourceVertices);
    expect(codes).toContain("collider-is-convex-hull");
    expect(codes).toContain("collider-decimated");
  });

  it("says so when centerOfMass could not be applied instead of implying it was", () => {
    const base = scene();
    const result = simulateScene(
      scene({ body: { ...base.body, centerOfMass: { x: 0, y: 0.18, z: 0 } } }),
      points,
      { runtime: "node", now: FIXED_CLOCK },
    );
    expect(result.notices.map((notice) => notice.code)).toContain("center-of-mass-not-applied");
  });

  it("reports the mass it was given, so a wrong mass is visible in the payload", () => {
    const result = simulateScene(scene(), points, { runtime: "node", now: FIXED_CLOCK });
    expect(result.collider.massKilograms).toBe(2.4);
  });

  it("bounds notices at the eight the contract allows", () => {
    const result = simulateScene(scene(), points, { runtime: "node", now: FIXED_CLOCK });
    expect(result.notices.length).toBeLessThanOrEqual(8);
  });
});
