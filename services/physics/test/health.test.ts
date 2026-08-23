import { beforeAll, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";
import { compileValidator, healthSchema, type HealthReport } from "@rinne/contracts";
import { buildApp } from "../src/app.js";
import { loadEnv } from "../src/config.js";
import { initPhysics, selfTest } from "../src/physics/engine.js";

const assertHealth = compileValidator<HealthReport>(healthSchema);

describe("health routes", () => {
  let app: FastifyInstance;

  beforeAll(async () => {
    await initPhysics();
    selfTest();

    // A hermetic environment, NOT { ...process.env }. Inheriting the ambient
    // environment would let a stray K_REVISION on the developer's machine or on
    // a CI runner change the response shape and break the exact-keys assertion
    // below for reasons that have nothing to do with the code.
    app = await buildApp({
      env: loadEnv({
        NODE_ENV: "test",
        SERVICE_VERSION: "test-1",
        GCP_REGION: "asia-southeast1",
      }),
    });
    await app.ready();
  });

  it("GET /livez returns 200 and a contract-valid report", async () => {
    const response = await app.inject({ method: "GET", url: "/livez" });
    expect(response.statusCode).toBe(200);

    const report = assertHealth(response.json());
    expect(report.service).toBe("physics");
    expect(report.status).toBe("ok");
    expect(report.version).toBe("test-1");
  });

  it("GET /readyz returns 200 once Rapier has self-tested", async () => {
    const response = await app.inject({ method: "GET", url: "/readyz" });
    expect(response.statusCode).toBe(200);

    const report = assertHealth(response.json());
    expect(report.status).toBe("ok");
    expect(report.detail).toMatch(/Rapier .* settled a test cube/);
    expect(report.dependencies?.[0]).toMatchObject({ name: "rapier-wasm", status: "ok" });
  });

  it("emits ONLY the properties declared in the contract", async () => {
    // Fastify serialises responses with fast-json-stringify, which drops any
    // property not in the response schema. That is a free data-exfiltration
    // control - a field accidentally added to a response object (an internal
    // URL, a token, a stack fragment) never reaches the caller. This asserts it
    // rather than trusting it.
    const response = await app.inject({ method: "GET", url: "/livez" });
    expect(Object.keys(response.json() as object).sort()).toEqual(
      ["checkedAt", "region", "service", "status", "version"].sort(),
    );
  });

  it("sets the hardening headers", async () => {
    const response = await app.inject({ method: "GET", url: "/livez" });
    expect(response.headers["x-content-type-options"]).toBe("nosniff");
    expect(response.headers["content-security-policy"]).toContain("default-src 'none'");
  });

  it("returns a request id and no stack trace on an unknown route", async () => {
    const response = await app.inject({ method: "GET", url: "/does-not-exist" });
    expect(response.statusCode).toBe(404);

    const body = response.json() as { error: string; requestId: string };
    expect(body.requestId).toBeTruthy();
    expect(JSON.stringify(body)).not.toContain("at ");
  });

  it("refuses cross-origin requests by default", async () => {
    // PHYSICS_ALLOWED_ORIGINS defaults to empty, which must mean "no CORS at
    // all". The browser reaches physics through the Next.js server, which holds
    // the IAM identity; a browser talking to this service directly would mean an
    // ID token had reached client-side JavaScript.
    const response = await app.inject({
      method: "OPTIONS",
      url: "/livez",
      headers: {
        origin: "https://evil.example",
        "access-control-request-method": "GET",
      },
    });
    expect(response.headers["access-control-allow-origin"]).toBeUndefined();
  });
});
