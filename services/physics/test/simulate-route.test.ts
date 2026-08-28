import { beforeAll, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";
import type { SceneDescription } from "@rinne/contracts";
import { initScene } from "@rinne/scene";
import { buildApp } from "../src/app.js";
import { loadEnv } from "../src/config.js";
import type { MeshFetcher } from "../src/physics/mesh-fetch.js";
import { boxGlb } from "./mesh-fixture.js";

const SCENE: SceneDescription = {
  schemaVersion: 1,
  sceneId: "route-000001",
  units: { length: "m", mass: "kg" },
  gravity: { x: 0, y: -9.81, z: 0 },
  ground: { friction: 0.6, restitution: 0.1 },
  body: {
    mesh: { uri: "gs://rinne-artifacts-rinnehackathon/meshes/route-000001.glb", format: "glb" },
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

const env = loadEnv({ NODE_ENV: "test", SERVICE_VERSION: "test-1" });

async function appWith(fetchMesh: MeshFetcher): Promise<FastifyInstance> {
  return buildApp({ env, fetchMesh });
}

const serving: MeshFetcher = () => Promise.resolve({ kind: "ok", bytes: boxGlb() });

describe("POST /v1/simulate", () => {
  beforeAll(async () => {
    await initScene();
  });

  it("simulates a scene and returns a contract-valid result", async () => {
    const app = await appWith(serving);
    const response = await app.inject({ method: "POST", url: "/v1/simulate", payload: SCENE });
    await app.close();

    expect(response.statusCode).toBe(200);
    const body = response.json();
    expect(body.sceneId).toBe("route-000001");
    expect(body.host.runtime).toBe("node");
    expect(body.determinism.digest).toMatch(/^[a-f0-9]{16}$/);
    expect(["stable", "tipped", "slid", "inconclusive"]).toContain(body.outcome.verdict);
  });

  it("is deterministic across two identical requests", async () => {
    const app = await appWith(serving);
    const first = await app.inject({ method: "POST", url: "/v1/simulate", payload: SCENE });
    const second = await app.inject({ method: "POST", url: "/v1/simulate", payload: SCENE });
    await app.close();

    expect(second.json().determinism.digest).toBe(first.json().determinism.digest);
  });

  it("REFUSES a non-gs:// mesh uri at the contract boundary", async () => {
    const app = await appWith(serving);
    const response = await app.inject({
      method: "POST",
      url: "/v1/simulate",
      payload: {
        ...SCENE,
        body: {
          ...SCENE.body,
          mesh: { uri: "http://metadata.google.internal/computeMetadata/v1/", format: "glb" },
        },
      },
    });
    await app.close();
    expect(response.statusCode).toBe(400);
  });

  it("refuses an unbounded simulation", async () => {
    const app = await appWith(serving);
    const response = await app.inject({
      method: "POST",
      url: "/v1/simulate",
      payload: { ...SCENE, solver: { ...SCENE.solver, maxSteps: 10_000_000 } },
    });
    await app.close();
    expect(response.statusCode).toBe(400);
  });

  it("returns 404 when the mesh is not in the bucket", async () => {
    const app = await appWith(() => Promise.resolve({ kind: "not-found" }));
    const response = await app.inject({ method: "POST", url: "/v1/simulate", payload: SCENE });
    await app.close();
    expect(response.statusCode).toBe(404);
    expect(response.json().error).toBe("mesh not found");
  });

  it("returns 422 and names the rule when the mesh will not decode", async () => {
    const app = await appWith(() => Promise.resolve({ kind: "ok", bytes: new Uint8Array(40) }));
    const response = await app.inject({ method: "POST", url: "/v1/simulate", payload: SCENE });
    await app.close();
    expect(response.statusCode).toBe(422);
    expect(response.json().error).toBe("mesh is not a GLB");
  });

  it("returns 400 and names the rule when the uri leaves our bucket", async () => {
    const app = await appWith(() =>
      Promise.resolve({ kind: "rejected", rule: "mesh uri points outside the artifacts bucket" }),
    );
    const response = await app.inject({ method: "POST", url: "/v1/simulate", payload: SCENE });
    await app.close();
    expect(response.statusCode).toBe(400);
  });
});
