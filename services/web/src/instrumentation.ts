export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  const { getServerEnv } = await import("./env.js");
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
}