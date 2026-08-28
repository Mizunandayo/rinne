import { z } from "zod";

const EnvSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().int().min(1).max(65535).default(8081),
  HOST: z.string().min(1).default("0.0.0.0"),
  LOG_LEVEL: z.enum(["fatal", "error", "warn", "info", "debug", "trace"]).default("info"),

  SERVICE_VERSION: z.string().min(1).max(64).default("0.0.0-dev"),
  GCP_REGION: z.string().min(1).max(32).default("asia-southeast1"),
  K_REVISION: z.string().max(128).optional(),

  BODY_LIMIT_BYTES: z.coerce.number().int().min(1024).max(5_242_880).default(1_048_576),
  REQUEST_TIMEOUT_MS: z.coerce.number().int().min(1000).max(120_000).default(30_000),
  SHUTDOWN_GRACE_MS: z.coerce.number().int().min(1000).max(30_000).default(9_000),

  RATE_LIMIT_MAX: z.coerce.number().int().min(1).max(10_000).default(120),
  RATE_LIMIT_WINDOW_MS: z.coerce.number().int().min(1000).max(3_600_000).default(60_000),

  PHYSICS_ALLOWED_ORIGINS: z.string().default(""),

  GCS_ARTIFACTS_BUCKET: z
    .string()
    .min(3)
    .max(63)
    .regex(/^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$/, "GCS_ARTIFACTS_BUCKET must be a bucket name")
    .default("rinne-artifacts-rinnehackathon"),

  // A stub GLB is ~350KB and a TripoSR one a few MB. Well under the ceiling.
  MAX_MESH_BYTES: z.coerce.number().int().min(1024).max(33_554_432).default(33_554_432),
  MESH_FETCH_TIMEOUT_MS: z.coerce.number().int().min(1000).max(120_000).default(30_000),

  // Local development only. On Cloud Run the token comes from the metadata server.
  RINNE_DEV_ACCESS_TOKEN: z.string().optional(),
});

export type Env = Readonly<z.infer<typeof EnvSchema>>;

export function loadEnv(source: NodeJS.ProcessEnv = process.env): Env {
  const parsed = EnvSchema.safeParse(source);

  if (!parsed.success) {
    const issues = parsed.error.issues
      .map((issue) => `  - ${issue.path.join(".") || "(root)"}: ${issue.message}`)
      .join("\n");
    throw new Error(`services/physics: invalid environment. Refusing to start.\n${issues}`);
  }

  return Object.freeze(parsed.data);
}

export function parseOrigins(raw: string): string[] {
  return raw
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
}

/** K_SERVICE is set by Cloud Run and by nothing else. */
export function isCloudRun(source: NodeJS.ProcessEnv = process.env): boolean {
  return typeof source["K_SERVICE"] === "string" && source["K_SERVICE"].length > 0;
}
