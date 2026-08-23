import { buildApp } from "./app.js";
import { loadEnv } from "./config.js";
import { initPhysics, selfTest } from "./physics/engine.js";

async function main(): Promise<void> {
  const env = loadEnv();

  await initPhysics();
  const result = selfTest();

  const app = await buildApp({ env });

  app.log.info(
    { steps: result.steps, restingY: result.restingY, durationMs: result.durationMs },
    "rapier self-test passed",
  );

  await app.listen({ host: env.HOST, port: env.PORT });

  let closing = false;

  const shutdown = (signal: NodeJS.Signals): void => {
    if (closing) return;
    closing = true;
    app.log.info({ signal }, "shutdown requested");

    const watchdog = setTimeout(() => {
      app.log.error("graceful shutdown timed out, exiting");
      process.exit(1);
    }, env.SHUTDOWN_GRACE_MS);
    watchdog.unref();

    app
      .close()
      .then(() => {
        clearTimeout(watchdog);
        app.log.info("closed cleanly");
        process.exit(0);
      })
      .catch((error: unknown) => {
        app.log.error({ err: error }, "error during shutdown");
        process.exit(1);
      });
  };

  process.once("SIGTERM", shutdown);
  process.once("SIGINT", shutdown);

  // A swallowed rejection leaves the process alive in an undefined state,
  process.on("unhandledRejection", (reason) => {
    app.log.fatal({ err: reason }, "unhandled rejection");
    process.exit(1);
  });
  process.on("uncaughtException", (error) => {
    app.log.fatal({ err: error }, "uncaught exception");
    process.exit(1);
  });
}

main().catch((error: unknown) => {
  console.error(
    JSON.stringify({
      severity: "CRITICAL",
      message: "services/physics failed to start",
      error: error instanceof Error ? error.message : String(error),
    }),
  );
  process.exit(1);
});
