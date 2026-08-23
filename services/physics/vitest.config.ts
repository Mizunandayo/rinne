import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["test/**/*.test.ts"],
    // Rapier's WASM instantiation is slow on a cold CI runner.
    testTimeout: 20_000,
    hookTimeout: 20_000,
    pool: "forks",
  },
});