// services/web/test/health.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { HealthReport } from "@rinne/contracts";

const VALID: HealthReport = {
  service: "physics",
  status: "ok",
  version: "0.1.0",
  checkedAt: "2026-08-16T04:20:00.000Z",
  region: "asia-southeast1",
};

function jsonResponse(body: unknown, status = 200): Response {
  const text = JSON.stringify(body);
  return new Response(text, {
    status,
    headers: { "content-type": "application/json", "content-length": String(text.length) },
  });
}

describe("probeService", () => {
  beforeEach(() => {
    vi.resetModules();
    process.env = {
      ...process.env,
      NODE_ENV: "test",
      PHYSICS_SERVICE_URL: "https://rinne-physics.example.run.app",
      AGENT_SERVICE_URL: "https://rinne-agent.example.run.app",
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the validated report when the service answers correctly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(VALID)));
    const { probeService } = await import("../src/lib/health.js");
    const result = await probeService("physics", "https://rinne-physics.example.run.app");
    expect(result.kind).toBe("reached");
  });

  it("reports 403 as 'forbidden', which is the expected unauthenticated result", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 403 })));
    const { probeService } = await import("../src/lib/health.js");
    const result = await probeService("physics", "https://rinne-physics.example.run.app");
    expect(result).toMatchObject({ kind: "unreachable", reason: "forbidden" });
  });

  it("rejects a response that violates the contract", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ service: "physics" })));
    const { probeService } = await import("../src/lib/health.js");
    const result = await probeService("physics", "https://rinne-physics.example.run.app");
    expect(result).toMatchObject({ kind: "unreachable", reason: "contract violation" });
  });

  it("rejects a report that claims to be a different service", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ...VALID, service: "agent" })));
    const { probeService } = await import("../src/lib/health.js");
    const result = await probeService("physics", "https://rinne-physics.example.run.app");
    expect(result).toMatchObject({ kind: "unreachable", reason: "contract violation" });
  });

  it("never leaks a raw error message to the caller", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("connect ECONNREFUSED 10.128.0.7:8081")),
    );
    const { probeService } = await import("../src/lib/health.js");
    const result = await probeService("physics", "https://rinne-physics.example.run.app");
    expect(JSON.stringify(result)).not.toContain("10.128.0.7");
  });
});
