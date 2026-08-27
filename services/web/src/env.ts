import "server-only";
import { z } from "zod";

/**
 * An absolute http(s) URL.
 *
 * `z.string().url()` alone is NOT enough. It defers to `new URL()`, and
 * `new URL("localhost:8080")` parses happily - "localhost:" becomes the scheme
 * and "8080" the path. A typo like that would clear boot validation and then
 * fail on the first outbound fetch in production, which is exactly the failure
 * mode fail-fast-at-boot exists to prevent.
 *
 * Constraining the protocol also rules out file:, data: and friends reaching a
 * server-side fetch through an environment variable.
 */
const httpUrl = (name: string) =>
  z
    .string()
    .url(`${name} must be an absolute URL`)
    .refine(
      (value) => {
        try {
          const { protocol } = new URL(value);
          return protocol === "http:" || protocol === "https:";
        } catch {
          return false;
        }
      },
      { message: `${name} must use http:// or https://` },
    );

const ServerEnvSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),

  PHYSICS_SERVICE_URL: httpUrl("PHYSICS_SERVICE_URL"),
  AGENT_SERVICE_URL: httpUrl("AGENT_SERVICE_URL"),
  RECONSTRUCTION_SERVICE_URL: httpUrl("RECONSTRUCTION_SERVICE_URL"),

  // Bucket name only. The web service reads objects through the JSON API with a
  // read_only token; it never holds a path it did not build itself.
  GCS_ARTIFACTS_BUCKET: z
    .string()
    .min(3)
    .max(63)
    .regex(/^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$/, "GCS_ARTIFACTS_BUCKET must be a bucket name"),

  SERVICE_VERSION: z.string().min(1).max(64).default("0.0.0-dev"),
  GCP_REGION: z.string().min(1).max(32).default("asia-southeast1"),

  K_SERVICE: z.string().optional(),
  K_REVISION: z.string().optional(),

  RINNE_DEV_ID_TOKEN: z.string().optional(),
  RINNE_DEV_ACCESS_TOKEN: z.string().optional(),
  HEALTH_TIMEOUT_MS: z.coerce.number().int().min(500).max(30000).default(4000),

  // A cold L4 can take most of the startup-probe budget to answer, so this is
  // deliberately far longer than HEALTH_TIMEOUT_MS.
  RECONSTRUCT_TIMEOUT_MS: z.coerce.number().int().min(5000).max(300000).default(240000),

  // Fixed window, in memory, per instance. The GLOBAL cap is the one protecting
  // the credit balance; a per-IP cap alone is trivially defeated.
  RATE_LIMIT_WINDOW_MS: z.coerce.number().int().min(1000).max(3600000).default(300000),
  RATE_LIMIT_PER_IP: z.coerce.number().int().min(1).max(1000).default(6),
  RATE_LIMIT_GLOBAL: z.coerce.number().int().min(1).max(10000).default(20),
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
