import type { FastifyInstance, FastifyPluginAsync } from "fastify";
import { healthSchema, toRouteSchema, type HealthReport } from "@rinne/contracts";
import { isReady, lastResult, initFailureReason, rapierVersion } from "../physics/engine.js";
import type { Env } from "../config.js";



export function healthRoutes(env: Env): FastifyPluginAsync {
  const responseSchema = toRouteSchema(healthSchema);

  const base = (): Omit<HealthReport, "status"> => ({
    service: "physics",
    version: env.SERVICE_VERSION,
    checkedAt: new Date().toISOString(),
    region: env.GCP_REGION,
    ...(env.K_REVISION !== undefined ? { revision: env.K_REVISION } : {}),
  });

  // FastifyPluginAsync is typed as (instance, opts) => Promise<void>, so this
  // function must be async even though registering routes awaits nothing.
  // eslint-disable-next-line @typescript-eslint/require-await
  return async (app: FastifyInstance): Promise<void> => {
    app.get(
      "/healthz",
      {
        schema: { response: { 200: responseSchema } },
        config: { rateLimit: false }, // probes must never be throttled
      },
      (): HealthReport => ({ ...base(), status: "ok" }),
    );

    app.get(
      "/readyz",
      {
        schema: { response: { 200: responseSchema, 503: responseSchema } },
        config: { rateLimit: false },
      },
      async (_request, reply): Promise<HealthReport> => {
        const ready = isReady();
        const result = lastResult();

        if (!ready) {
          void reply.code(503);
          return {
            ...base(),
            status: "down",
            detail: `Rapier not ready: ${initFailureReason() ?? "self-test has not run"}`,
            dependencies: [{ name: "rapier-wasm", status: "down" }],
          };
        }

        return {
          ...base(),
          status: "ok",
          detail: `Rapier ${rapierVersion()} settled a test cube at y=${result?.restingY.toFixed(3) ?? "?"}`,
          dependencies: [
            {
              name: "rapier-wasm",
              status: "ok",
              ...(result !== undefined && result !== null ? { latencyMs: result.durationMs } : {}),
            },
          ],
        };
      },
    );
  };
}