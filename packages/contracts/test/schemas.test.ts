import { describe, expect, it } from "vitest";
import _Ajv from "ajv";
import _addFormats from "ajv-formats";

// Same CommonJS/ESM interop as src/validate.ts - see the note there.
const Ajv = _Ajv as unknown as typeof _Ajv.default;
const addFormats = _addFormats as unknown as typeof _addFormats.default;
import {
  agentJobSchema,
  healthSchema,
  reconstructionRequestSchema,
  reconstructionResultSchema,
  sceneDescriptionSchema,
  simulationResultSchema,
} from "../src/generated/schemas.js";
import { compileValidator, ContractViolationError } from "../src/validate.js";
import type { HealthReport } from "../src/generated/health.js";
import type { SceneDescription } from "../src/generated/scene-description.js";

const allSchemas = [
  ["agent-job", agentJobSchema],
  ["health", healthSchema],
  ["reconstruction-request", reconstructionRequestSchema],
  ["reconstruction-result", reconstructionResultSchema],
  ["scene-description", sceneDescriptionSchema],
  ["simulation-result", simulationResultSchema],
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

  it("no two schemas claim the same generated type name", () => {
    // src/generated/index.ts re-exports every module FLAT, so every definitions
    // key and every titled oneOf member becomes one global TypeScript
    // identifier. A collision is a tsc error at build time, not a lint warning,
    // and it appears in a generated file nobody edits - so it is caught here
    // instead, where the message says which schema to rename.
    const seen = new Map<string, string>();
    const collisions: string[] = [];

    for (const [name, schema] of allSchemas) {
      const declared: string[] = [schema.title];

      const definitions = (schema as { definitions?: Record<string, unknown> }).definitions ?? {};
      declared.push(...Object.keys(definitions));

      const visit = (node: unknown): void => {
        if (typeof node !== "object" || node === null) return;
        for (const [key, value] of Object.entries(node)) {
          if (key === "oneOf" || key === "anyOf") {
            for (const member of value as unknown[]) {
              const title = (member as { title?: string }).title;
              if (typeof title === "string") declared.push(title);
            }
          }
          visit(value);
        }
      };
      visit(schema);

      for (const identifier of declared) {
        // Definition keys are camelCase in the schema and PascalCase in the
        // generated module, so compare case-insensitively or the check misses
        // exactly the collisions it exists to find.
        const key = identifier.toLowerCase();
        const owner = seen.get(key);
        if (owner !== undefined && owner !== name) {
          collisions.push(`${identifier}: ${owner} and ${name}`);
        }
        seen.set(key, name);
      }
    }

    expect(collisions, "definition names collide in the flat barrel").toEqual([]);
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
    expect(() => assertScene({ ...scene, body: { ...scene.body, massKilograms: 0 } })).toThrow(
      ContractViolationError,
    );
  });
});
