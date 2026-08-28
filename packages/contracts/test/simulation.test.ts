import { describe, expect, it } from "vitest";
import { simulationResultSchema } from "../src/generated/schemas.js";
import { compileValidator, ContractViolationError } from "../src/validate.js";
import type { SimulationResult } from "../src/generated/simulation-result.js";

const assertResult = compileValidator<SimulationResult>(simulationResultSchema);

const result: SimulationResult = {
  schemaVersion: 1,
  sceneId: "parity-000001",
  completedAt: "2026-08-28T04:00:00.000Z",
  host: { runtime: "node", engine: "rapier3d-compat", engineVersion: "0.14.0" },
  outcome: {
    verdict: "tipped",
    settled: true,
    steps: 194,
    simulatedSeconds: 3.233333,
    tiltDegrees: 90.07,
    driftMeters: 1.054,
  },
  finalPose: {
    translation: { x: 1.054, y: 0.1, z: 0 },
    rotation: { x: 0, y: 0, z: 0.707107, w: 0.707107 },
  },
  collider: { kind: "convex-hull", sourceVertices: 3752, hullVertices: 152, massKilograms: 2.4 },
  determinism: { seed: 42, timestepSeconds: 0.016667, substeps: 4, digest: "10b6c77410897fcc" },
  timings: { setupMs: 4, stepMs: 61, totalMs: 66 },
};

describe("SimulationResult", () => {
  it("accepts a well-formed result", () => {
    expect(assertResult(result)).toEqual(result);
  });

  it("rejects an unknown property, so a typo cannot pass silently", () => {
    expect(() => assertResult({ ...result, verdict: "tipped" })).toThrow(ContractViolationError);
  });

  it("rejects a verdict outside the closed enum the agent branches on", () => {
    expect(() =>
      assertResult({ ...result, outcome: { ...result.outcome, verdict: "exploded" } }),
    ).toThrow(ContractViolationError);
  });

  it("REJECTS a digest that is not sixteen hex characters", () => {
    // The digest is the parity claim in one string. A malformed one would make
    // two hosts trivially "agree" by both being wrong.
    for (const digest of ["", "not-hex", "10B6C77410897FCC", "10b6c77410897fc"]) {
      expect(() =>
        assertResult({ ...result, determinism: { ...result.determinism, digest } }),
      ).toThrow(ContractViolationError);
    }
  });

  it("rejects a tilt outside 0-180 degrees", () => {
    expect(() =>
      assertResult({ ...result, outcome: { ...result.outcome, tiltDegrees: 181 } }),
    ).toThrow(ContractViolationError);
  });

  it("bounds notices at eight", () => {
    const notice = { code: "did-not-settle", severity: "warning", message: "x" } as const;
    expect(() =>
      assertResult({ ...result, notices: Array.from({ length: 9 }, () => notice) }),
    ).toThrow(ContractViolationError);
  });

  it("rejects a notice code outside the closed enum", () => {
    expect(() =>
      assertResult({
        ...result,
        notices: [{ code: "something-went-wrong", severity: "warning", message: "x" }],
      }),
    ).toThrow(ContractViolationError);
  });

  it("rejects a sceneId that could escape a Firestore document key", () => {
    expect(() => assertResult({ ...result, sceneId: "../../etc/passwd" })).toThrow(
      ContractViolationError,
    );
  });

  it("requires the host block, because a result must say which side produced it", () => {
    const clone: Record<string, unknown> = { ...result };
    delete clone["host"];
    expect(() => assertResult(clone)).toThrow(ContractViolationError);
  });
});
