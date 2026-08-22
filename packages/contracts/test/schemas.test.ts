import { describe, expect, it } from "vitest";
import Ajv from "ajv";
import addFormats from "ajv-formats";
import { healthSchema, sceneDescriptionSchema } from "../src/generated/schemas.js";
import { compileValidator, ContractViolationError } from "../src/validate.js";
import type { HealthReport } from "../src/generated/health.js";
import type { SceneDescription } from "../src/generated/scene-description.js";

const allSchemas = [
  ["health", healthSchema],
  ["scene-description", sceneDescriptionSchema],
] as const;

describe("schema hygiene", () => {
  it("every schema compiles under Ajv strict mode", () => {
    for (const [name, schema] of allSchemas) {
      const strict = new Ajv({ strict: true, allErrors: true });
      addFormats(strict);
      expect(() => strict.compile(schema), `${name} failed strict compilation`).not.toThrow();
    }
  });

  it("every schema declares a title, an $id, and forbids additional properties", () => {
    for (const [name, schema] of allSchemas) {
      expect(schema.title, `${name} is missing title`).toBeTruthy();
      expect(schema.$id, `${name} is missing $id`).toBeTruthy();
      expect(
        (schema as { additionalProperties?: boolean }).additionalProperties,
        `${name} allows additional properties`,
      ).toBe(false);
    }
  });
});

describe("HealthReport", () => {
  const assertHealth = compileValidator<HealthReport>(healthSchema);

  const valid: HealthReport = {
    service: "physics",
    status: "ok",
    version: "0.1.0",
    checkedAt: "2026-08-16T04:20:00.000Z",
  };

  it("accepts a minimal valid report", () => {
    expect(assertHealth(valid)).toEqual(valid);
  });

  it("rejects an unknown service name", () => {
    expect(() => assertHealth({ ...valid, service: "reconstruction-v2" })).toThrow(
      ContractViolationError,
    );
  });

  it("rejects an unknown property, so a typo cannot pass silently", () => {
    expect(() => assertHealth({ ...valid, statuss: "ok" })).toThrow(ContractViolationError);
  });

  it("rejects a non-RFC-3339 timestamp", () => {
    expect(() => assertHealth({ ...valid, checkedAt: "16/08/2026" })).toThrow(
      ContractViolationError,
    );
  });
});

describe("SceneDescription", () => {
  const assertScene = compileValidator<SceneDescription>(sceneDescriptionSchema);

  const scene: SceneDescription = {
    schemaVersion: 1,
    sceneId: "scan-000001",
    units: { length: "m", mass: "kg" },
    gravity: { x: 0, y: -9.81, z: 0 },
    ground: { friction: 0.6, restitution: 0.1 },
    body: {
      mesh: { uri: "gs://rinne-scans/meshes/scan-000001.glb", format: "glb" },
      massKilograms: 2.4,
      friction: 0.55,
      restitution: 0.05,
      initialTranslation: { x: 0, y: 0.5, z: 0 },
    },
    test: { kind: "tip", pushHeightRatio: 0.8, forceNewtons: 12, directionDegrees: 90 },
    solver: { timestepSeconds: 1 / 60, maxSteps: 900, seed: 42 },
  };

  it("accepts a well-formed tip-test scene", () => {
    expect(assertScene(scene)).toEqual(scene);
  });

  it("REJECTS a non-gs:// mesh URI — this is the SSRF control, not a style rule", () => {
    expect(() =>
      assertScene({
        ...scene,
        body: {
          ...scene.body,
          mesh: {
            uri: "http://metadata.google.internal/computeMetadata/v1/",
            format: "glb",
          },
        },
      }),
    ).toThrow(ContractViolationError);
  });

  it("rejects an unbounded simulation, per the no-unbounded-loops rule", () => {
    expect(() =>
      assertScene({ ...scene, solver: { ...scene.solver, maxSteps: 10_000_000 } }),
    ).toThrow(ContractViolationError);
  });

  it("rejects a test object that mixes two test kinds", () => {
    expect(() =>
      assertScene({
        ...scene,
        test: {
          kind: "tip",
          pushHeightRatio: 0.8,
          forceNewtons: 12,
          directionDegrees: 90,
          loadKilograms: 5,
        } as unknown as SceneDescription["test"],
      }),
    ).toThrow(ContractViolationError);
  });

  it("rejects a zero mass", () => {
    expect(() =>
      assertScene({ ...scene, body: { ...scene.body, massKilograms: 0 } }),
    ).toThrow(ContractViolationError);
  });
});
