/**
 * services/web/src/instrumentation.ts
 *
 * register() runs once when the Next.js server starts, which makes it the right
 * place to validate configuration.
 *
 * THE EXPLICIT process.exit(1) IS LOAD-BEARING. Next.js CATCHES an exception
 * thrown from register(), logs "Failed to prepare server", and then leaves the
 * process running and listening on the port. On Cloud Run that is the worst
 * possible outcome: the container passes the default TCP startup probe, the
 * revision is promoted to serve traffic, and every single request then fails
 * with a 500 from getServerEnv().
 *
 * Verified empirically: without the exit, `docker run` of this image with no
 * environment reports `running=true` and "Ready in 465ms" alongside the
 * validation error. Exiting is what actually makes the revision fail to start,
 * so traffic is never shifted to it.
 *
 * Pair this with an explicit Cloud Run startup probe on /api/health rather than
 * relying on the default TCP check.
 */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  const { getServerEnv } = await import("./env");

  try {
    const env = getServerEnv();

    console.error(
      JSON.stringify({
        severity: "INFO",
        message: "rinne-web starting",
        service: "web",
        version: env.SERVICE_VERSION,
        revision: env.K_REVISION ?? "local",
        region: env.GCP_REGION,
        // URLs are logged; tokens never are.
        physics: env.PHYSICS_SERVICE_URL,
        agent: env.AGENT_SERVICE_URL,
      }),
    );
  } catch (error) {
    console.error(
      JSON.stringify({
        severity: "CRITICAL",
        message: error instanceof Error ? error.message : String(error),
        service: "web",
      }),
    );
    // Do not rethrow: Next.js would swallow it and keep serving.
    process.exit(1);
  }
}
