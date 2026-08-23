import { beforeAll, describe, expect, it } from "vitest";
import { initPhysics, selfTest, isReady, rapierVersion } from "../src/physics/engine.js";

describe("Rapier engine", () => {
  beforeAll(async () => {
    await initPhysics();
  });

  it("reports a version once initialised", () => {
    expect(rapierVersion()).toMatch(/^\d+\.\d+/);
  });

  it("settles a dropped cube at its half-extent above the ground", () => {
    const result = selfTest();
    expect(result.restingY).toBeGreaterThan(0.45);
    expect(result.restingY).toBeLessThan(0.55);
    expect(result.steps).toBe(240);
  });

  it("is deterministic: the same construction gives the same resting position", () => {
    const a = selfTest();
    const b = selfTest();
    // The shared-engine claim in §6 is only true if this holds. When the
    expect(a.restingY).toBeCloseTo(b.restingY, 9);
  });

  it("becomes ready only after a successful self-test", () => {
    expect(isReady()).toBe(true);
  });
});
