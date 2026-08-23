/**
 * Test stub for the `server-only` package.
 *
 * `server-only` throws on import BY DESIGN unless a bundler selects its
 * `react-server` export condition. That guard is what makes an accidental
 * `import "@/env"` from a Client Component a build error rather than a leaked
 * secret, so it must stay in place for the real Next.js build.
 *
 * Vitest runs in plain Node, where no bundler applies that condition, so every
 * server-side unit test would fail on import. Aliasing the package to this empty
 * module in vitest.config.ts restores testability without weakening the guard:
 * `next build` still resolves the real package and still fails correctly.
 */
export {};
