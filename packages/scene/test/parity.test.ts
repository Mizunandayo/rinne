/* THE DAY 3 MILESTONE, asserted. */

import { beforeAll, describe, expect, it } from "vitest";
import type { SceneDescription } from "@rinne/contracts";
import { readPositions } from "../src/glb.js";
import { initScene } from "../src/world.js";
import { simulateScene } from "../src/simulate.js";
import { boxGlb } from "./fixture.js";

const SCENE: SceneDescription = {
  schemaVersion: 1,
  sceneId: "parity-000001",
  units: { length: "m", mass: "kg" },
  gravity: { x: 0, y: -9.81, z: 0 },
  ground: { friction: 0.6, restitution: 0.1 },
  body: {
    mesh: { uri: "gs://rinne-artifacts-rinnehackathon/meshes/parity-000001.glb", format: "glb" },
    massKilograms: 2.4,
    friction: 0.55,
    restitution: 0.05,
    initialTranslation: { x: 0, y: 0.02, z: 0 },
  },
  test: {
    kind: "tip",
    pushHeightRatio: 0.9,
    forceNewtons: 18,
    directionDegrees: 0,
    durationSeconds: 0.2,
  },
  solver: { timestepSeconds: 1 / 60, maxSteps: 900, substeps: 4, seed: 42 },
};

describe("parity: one scene, two hosts", () => {
  const points = readPositions(boxGlb());
  beforeAll(async () => {
    await initScene();
  });

  it("produces the same digest on the server and in the browser build", () => {
    const server = simulateScene(SCENE, points, { runtime: "node" });
    const browser = simulateScene(SCENE, points, { runtime: "browser" });

    expect(browser.determinism.digest).toBe(server.determinism.digest);
    expect(browser.outcome).toEqual(server.outcome);
    expect(browser.finalPose).toEqual(server.finalPose);
  });

  it("differs ONLY in the host block, which is the field that exists to say so", () => {
    const server = simulateScene(SCENE, points, { runtime: "node" });
    const browser = simulateScene(SCENE, points, { runtime: "browser" });

    expect(server.host.runtime).toBe("node");
    expect(browser.host.runtime).toBe("browser");
    expect(browser.host.engine).toBe(server.host.engine);
    expect(browser.host.engineVersion).toBe(server.host.engineVersion);
  });

  it("is stable across eight fresh worlds", () => {
    const digests = new Set<string>();
    for (let run = 0; run < 8; run += 1) {
      digests.add(simulateScene(SCENE, points, { runtime: "node" }).determinism.digest);
    }
    expect(digests.size).toBe(1);
  });

  it("excludes the wall clock from the digest", () => {
    const early = simulateScene(SCENE, points, {
      runtime: "node",
      now: () => new Date("2020-01-01T00:00:00.000Z"),
    });
    const late = simulateScene(SCENE, points, {
      runtime: "node",
      now: () => new Date("2031-12-31T23:59:59.000Z"),
    });

    expect(late.determinism.digest).toBe(early.determinism.digest);
    expect(late.completedAt).not.toBe(early.completedAt);
  });

  it("changes the digest when the scene changes, so equality means something", () => {
    const base = simulateScene(SCENE, points, { runtime: "node" });
    const harder = simulateScene(
      {
        ...SCENE,
        test: {
          kind: "tip",
          pushHeightRatio: 0.9,
          forceNewtons: 6,
          directionDegrees: 0,
          durationSeconds: 0.2,
        },
      },
      points,
      { runtime: "node" },
    );
    expect(harder.determinism.digest).not.toBe(base.determinism.digest);
  });

  it("carries the solver settings needed to reproduce it", () => {
    const result = simulateScene(SCENE, points, { runtime: "node" });
    expect(result.determinism.seed).toBe(42);
    expect(result.determinism.timestepSeconds).toBe(1 / 60);
    expect(result.determinism.substeps).toBe(4);
    expect(result.determinism.digest).toMatch(/^[a-f0-9]{16}$/);
  });
});
