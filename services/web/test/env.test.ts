import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const BASE = {
  NODE_ENV: "test",
  PHYSICS_SERVICE_URL: "https://rinne-physics.example.run.app",
  AGENT_SERVICE_URL: "https://rinne-agent.example.run.app",
} as const;

describe("getServerEnv", () => {
  const original = process.env;

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...original };
  });

  afterEach(() => {
    process.env = original;
  });

  it("accepts a complete environment and applies defaults", async () => {
    process.env = { ...process.env, ...BASE };
    const { getServerEnv } = await import("../src/env.js");
    const env = getServerEnv();
    expect(env.HEALTH_TIMEOUT_MS).toBe(4000);
    expect(env.GCP_REGION).toBe("asia-southeast1");
  });

  it("throws when a service URL is missing, so the container never starts", async () => {
    process.env = { ...process.env, ...BASE, PHYSICS_SERVICE_URL: undefined };
    const { getServerEnv } = await import("../src/env.js");
    expect(() => getServerEnv()).toThrow(/PHYSICS_SERVICE_URL/);
  });

  it("throws when a service URL is not absolute", async () => {
    process.env = { ...process.env, ...BASE, AGENT_SERVICE_URL: "localhost:8080" };
    const { getServerEnv } = await import("../src/env.js");
    expect(() => getServerEnv()).toThrow(/AGENT_SERVICE_URL/);
  });

  it("never echoes an offending value into the error message", async () => {
    process.env = { ...process.env, ...BASE, AGENT_SERVICE_URL: "not-a-url-SENSITIVE" };
    const { getServerEnv } = await import("../src/env.js");
    expect(() => getServerEnv()).toThrow();
    try {
      getServerEnv();
    } catch (error) {
      expect(String(error)).not.toContain("SENSITIVE");
    }
  });
});
