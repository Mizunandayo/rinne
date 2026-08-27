import { describe, expect, it } from "vitest";
import {
  reconstructionRequestSchema,
  reconstructionResultSchema,
} from "../src/generated/schemas.js";
import { compileValidator, ContractViolationError } from "../src/validate.js";
import type { ReconstructionRequest } from "../src/generated/reconstruction-request.js";
import type { ReconstructionResult } from "../src/generated/reconstruction-result.js";

/**
 * Drop keys from a fixture to build an invalid document.
 *
 * The obvious spelling - `const { mesh: _mesh, ...rest } = result` - is not
 * available: @typescript-eslint/no-unused-vars reports the renamed sibling as
 * assigned-but-never-used even though a rest element is present, and the repo
 * lints tests. One helper, used everywhere, keeps the tests readable and the
 * lint honest.
 */
function without<T extends object, K extends keyof T>(base: T, ...keys: readonly K[]): Omit<T, K> {
  const clone: Record<string, unknown> = { ...base };
  for (const key of keys) delete clone[key as string];
  return clone as Omit<T, K>;
}

/** Sum at 4dp, matching the precision every component is rounded to. */
const sumAt4dp = (weights: Record<string, number>): number =>
  Number(
    Object.values(weights)
      .reduce((total, weight) => total + weight, 0)
      .toFixed(4),
  );

const assertRequest = compileValidator<ReconstructionRequest>(reconstructionRequestSchema);
const assertResult = compileValidator<ReconstructionResult>(reconstructionResultSchema);

describe("ReconstructionRequest", () => {
  const request: ReconstructionRequest = {
    schemaVersion: 1,
    requestId: "scan-000001",
  };

  it("accepts the minimal valid request", () => {
    expect(assertRequest(request)).toEqual(request);
  });

  it("accepts every optional field together", () => {
    const full: ReconstructionRequest = {
      ...request,
      capturedAt: "2026-08-24T09:15:00.000Z",
      assumedLongestDimensionMeters: 0.3,
      label: "Desk plank, front three-quarter",
      metadata: { capture: "handheld", surface: "wood" },
    };
    expect(assertRequest(full)).toEqual(full);
  });

  it("REJECTS a requestId that could escape the meshes/ prefix", () => {
    // requestId becomes the GCS object name. A slash or a dot-dot here is a
    // path-traversal primitive aimed at the bucket, so it dies at the contract
    // boundary rather than in whichever handler happens to concatenate it.
    for (const requestId of ["../../etc/passwd", "scan/000001", "SCAN-000001", "short"]) {
      expect(() => assertRequest({ ...request, requestId }), requestId).toThrow(
        ContractViolationError,
      );
    }
  });

  it("rejects an unknown property, so a typo cannot pass silently", () => {
    expect(() => assertRequest({ ...request, requestID: "scan-000001" })).toThrow(
      ContractViolationError,
    );
  });

  it("rejects a zero or negative assumed dimension", () => {
    expect(() => assertRequest({ ...request, assumedLongestDimensionMeters: 0 })).toThrow(
      ContractViolationError,
    );
  });

  it("bounds metadata by property count", () => {
    const metadata = Object.fromEntries(
      Array.from({ length: 17 }, (_unused, index) => [`k${index}`, "v"]),
    );
    expect(() => assertRequest({ ...request, metadata })).toThrow(ContractViolationError);
  });

  it("rejects a non-string metadata value", () => {
    expect(() => assertRequest({ ...request, metadata: { weight: 12 } })).toThrow(
      ContractViolationError,
    );
  });

  it("rejects an unrecognised schemaVersion rather than guessing", () => {
    expect(() => assertRequest({ ...request, schemaVersion: 2 })).toThrow(ContractViolationError);
  });
});

describe("ReconstructionResult", () => {
  /** The exact shape Day 2 ships: stub pipeline, three confidence components. */
  const result: ReconstructionResult = {
    schemaVersion: 1,
    requestId: "scan-000001",
    completedAt: "2026-08-24T09:15:04.120Z",
    mesh: {
      uri: "gs://rinne-artifacts-rinnehackathon/meshes/scan-000001.glb",
      format: "glb",
      byteLength: 48120,
      vertexCount: 1284,
      faceCount: 2564,
      watertight: true,
      extent: { x: 0.3, y: 0.12, z: 0.18 },
      volumeCubicMeters: 0.0031,
      upAxis: "y",
      scaleBasis: "assumed",
    },
    material: {
      name: "wood",
      basis: "heuristic-v1",
      confidence: 0.5,
      densityKilogramsPerCubicMeter: 600,
      massKilograms: 1.023,
      friction: 0.5,
      restitution: 0.2,
    },
    confidence: {
      score: 0.735,
      band: "medium",
      calibrated: false,
      components: {
        fieldDecisiveness: 0.7104,
        watertightness: 1.0,
        volumePlausibility: 0.0512,
      },
      weights: {
        fieldDecisiveness: 0.5294,
        watertightness: 0.3529,
        volumePlausibility: 0.1177,
      },
    },
    pipeline: { name: "stub", version: "stub-1", device: "cuda", seed: 42 },
    images: {
      received: 3,
      accepted: 3,
      used: 1,
      reencoded: true,
      longestEdgePixels: 1536,
    },
    timings: { validationMs: 84, inferenceMs: 0, meshMs: 41, uploadMs: 260, totalMs: 385 },
    notices: [
      {
        code: "stub-pipeline",
        severity: "warning",
        message: "Mesh produced by the stub pipeline.",
      },
      { code: "scale-assumed", severity: "info", message: "Scale assumed, not measured." },
    ],
  };

  it("accepts the Day 2 stub result", () => {
    expect(assertResult(result)).toEqual(result);
  });

  it("accepts the four-component result that lands with segmentation", () => {
    // The fourth component is additive, so TripoSR plus segmentation is a
    // config change rather than a schemaVersion bump. This asserts that.
    const withForeground: ReconstructionResult = {
      ...result,
      confidence: {
        ...result.confidence,
        components: { ...result.confidence.components, foregroundQuality: 0.8231 },
        weights: {
          fieldDecisiveness: 0.45,
          watertightness: 0.3,
          volumePlausibility: 0.1,
          foregroundQuality: 0.15,
        },
      },
      pipeline: { name: "triposr", version: "107cefdc244c", device: "cuda" },
    };
    expect(assertResult(withForeground)).toEqual(withForeground);
  });

  it("REJECTS a non-gs:// mesh URI - this is the SSRF control, not a style rule", () => {
    expect(() =>
      assertResult({
        ...result,
        mesh: { ...result.mesh, uri: "http://metadata.google.internal/computeMetadata/v1/" },
      }),
    ).toThrow(ContractViolationError);
  });

  it("requires every load-bearing section", () => {
    for (const key of [
      "mesh",
      "material",
      "confidence",
      "pipeline",
      "images",
      "timings",
    ] as const) {
      expect(() => assertResult(without(result, key)), key).toThrow(ContractViolationError);
    }
  });

  it("rejects a confidence score outside [0,1]", () => {
    expect(() =>
      assertResult({ ...result, confidence: { ...result.confidence, score: 1.2 } }),
    ).toThrow(ContractViolationError);
  });

  it("rejects a zero mass, matching the bound on rigidBody", () => {
    expect(() =>
      assertResult({ ...result, material: { ...result.material, massKilograms: 0 } }),
    ).toThrow(ContractViolationError);
  });

  it("rejects an unknown pipeline name, so a third reconstructor cannot appear unannounced", () => {
    expect(() =>
      assertResult({ ...result, pipeline: { ...result.pipeline, name: "triposr-v2" } }),
    ).toThrow(ContractViolationError);
  });

  it("rejects a free-text notice code", () => {
    expect(() =>
      assertResult({
        ...result,
        notices: [{ code: "something-went-wrong", severity: "info", message: "..." }],
      }),
    ).toThrow(ContractViolationError);
  });

  it("bounds the notices array", () => {
    const notices = Array.from({ length: 9 }, () => ({
      code: "scale-assumed",
      severity: "info",
      message: "Scale assumed, not measured.",
    }));
    expect(() => assertResult({ ...result, notices })).toThrow(ContractViolationError);
  });

  it("lets a consumer iterate notices without fighting the tuple union", () => {
    // maxItems makes the generated type a union of tuples. This is the Part 7
    // consumption pattern, asserted here so the UI does not discover it later.
    const validated = assertResult(result);
    const codes = (validated.notices ?? []).map((notice) => notice.code);
    expect(codes).toEqual(["stub-pipeline", "scale-assumed"]);
  });

  describe("confidence weights", () => {
    it("the Day 2 renormalised weights sum to exactly 1", () => {
      // 0.1177 is rounded UP from 0.117647 to absorb the residual. The naive
      // 0.1176 sums to 0.9999 and fails here, which is the point of the test.
      expect(sumAt4dp(result.confidence.weights)).toBe(1);
    });

    it("the full four-component weights sum to exactly 1", () => {
      expect(
        sumAt4dp({
          fieldDecisiveness: 0.45,
          watertightness: 0.3,
          foregroundQuality: 0.15,
          volumePlausibility: 0.1,
        }),
      ).toBe(1);
    });

    it("weights and components carry the same keys, so the score is recomputable", () => {
      const { components, weights, score } = result.confidence;
      expect(Object.keys(weights).sort()).toEqual(Object.keys(components).sort());

      const recomputed = Object.entries(weights).reduce(
        (total, [name, weight]) => total + weight * components[name as keyof typeof components]!,
        0,
      );
      expect(Number(recomputed.toFixed(4))).toBe(score);
    });
  });
});
