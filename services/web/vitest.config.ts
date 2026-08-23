import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";



export default defineConfig({
  test: {
    environment: "node",
    include: ["test/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      // `server-only` throws unless a bundler picks its `react-server` export
      // condition. Vitest is plain Node, so point it at a local empty stub.
      // The guard still works where it matters: `next build` resolves the real
      // package and still fails if a Client Component imports server code.
      "server-only": fileURLToPath(new URL("./test/stubs/server-only.ts", import.meta.url)),
    },
  },
});