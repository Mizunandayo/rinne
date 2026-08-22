import "server-only";
import { z } from "zod";

const ServerEnvSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),

  PHYSICS_SERVICE_URL: z.string().url("PHYSICS_SERVICE_URL must be an absolute URL"),
  AGENT_SERVICE_URL: z.string().url("AGENT_SERVICE_URL must be an absolute URL"),

  SERVICE_VERSION: z.string().min(1).max(64).default("0.0.0-dev"),
  GCP_REGION: z.string().min(1).max(32).default("asia-southeast1"),

  K_SERVICE: z.string().optional(),
  K_REVISION: z.string().optional(),

  RINNE_DEV_ID_TOKEN: z.string().optional(),
  HEALTH_TIMEOUT_MS: z.coerce.number().int().min(500).max(30000).default(4000),
});

export type ServerEnv = Readonly<z.infer<typeof ServerEnvSchema>>;

let cached: ServerEnv | undefined;

export function getServerEnv(): ServerEnv {
  if (cached) return cached;

  const parsed = ServerEnvSchema.safeParse(process.env);

  if (!parsed.success) {
    const issues = parsed.error.issues
      .map((issue) => `  - ${issue.path.join(".") || "(root)"}: ${issue.message}`)
      .join("\n");

  throw new Error(
      `services/web: invalid environment. Refusing to start.\n${issues}\n` +
        `See .env.example for the full set.`,
    );
  }

  cached = Object.freeze(parsed.data);
  return cached;
}

/** True when running on Cloud Run, as opposed to a local dev machine. */
export function isCloudRun(): boolean {
  return getServerEnv().K_SERVICE !== undefined;
}
