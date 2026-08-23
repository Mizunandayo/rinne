import "server-only";
import { compileValidator, healthSchema, type HealthReport } from "@rinne/contracts";
import { getServerEnv } from "../env";
import { getIdToken } from "./gcp-auth";

const assertHealthReport = compileValidator<HealthReport>(healthSchema);

/** A health payload has no business being large. */
const MAX_RESPONSE_BYTES = 16 * 1024;

export type ServiceName = HealthReport["service"];

export type ProbeOutcome =
  | {
      readonly kind: "reached";
      readonly service: ServiceName;
      readonly report: HealthReport;
      readonly latencyMs: number;
    }
  | {
      readonly kind: "unreachable";
      readonly service: ServiceName;
      readonly reason: UnreachableReason;
      readonly latencyMs: number;
    };

export type UnreachableReason =
  | "timed out"
  | "connection failed"
  | "unauthorized"
  | "forbidden"
  | "server error"
  | "response too large"
  | "contract violation";

function classify(error: unknown): UnreachableReason {
  if (error instanceof Error) {
    if (error.name === "TimeoutError" || error.name === "AbortError") return "timed out";
    if (error.name === "ContractViolationError") return "contract violation";
  }
  return "connection failed";
}

export async function probeService(service: ServiceName, baseUrl: string): Promise<ProbeOutcome> {
  const env = getServerEnv();
  const started = performance.now();
  const elapsed = (): number => Math.round(performance.now() - started);

  try {
    const target = new URL("/livez", baseUrl);
    const token = await getIdToken(baseUrl);

    const response = await fetch(target, {
      method: "GET",
      cache: "no-store",
      // A redirect from a downstream is never legitimate here, and following
      // one turns this probe into an SSRF primitive.
      redirect: "error",
      headers: {
        accept: "application/json",
        ...(token !== null ? { authorization: `Bearer ${token}` } : {}),
      },
      signal: AbortSignal.timeout(env.HEALTH_TIMEOUT_MS),
    });

    if (!response.ok) {
      const reason: UnreachableReason =
        response.status === 401
          ? "unauthorized"
          : response.status === 403
            ? "forbidden"
            : "server error";
      return { kind: "unreachable", service, reason, latencyMs: elapsed() };
    }

    const declaredLength = Number(response.headers.get("content-length") ?? "0");
    if (declaredLength > MAX_RESPONSE_BYTES) {
      return { kind: "unreachable", service, reason: "response too large", latencyMs: elapsed() };
    }

    const text = await response.text();
    if (text.length > MAX_RESPONSE_BYTES) {
      return { kind: "unreachable", service, reason: "response too large", latencyMs: elapsed() };
    }

    const report = assertHealthReport(JSON.parse(text) as unknown);

    // A service that misreports its own identity is a routing or deploy bug,
    // and catching it here is much cheaper than catching it on Day 5.
    if (report.service !== service) {
      return { kind: "unreachable", service, reason: "contract violation", latencyMs: elapsed() };
    }

    return { kind: "reached", service, report, latencyMs: elapsed() };
  } catch (error) {
    console.error(
      JSON.stringify({
        severity: "ERROR",
        message: "health probe failed",
        service,
        reason: classify(error),
      }),
    );
    return { kind: "unreachable", service, reason: classify(error), latencyMs: elapsed() };
  }
}

export function localHealthReport(): HealthReport {
  const env = getServerEnv();
  return {
    service: "web",
    status: "ok",
    version: env.SERVICE_VERSION,
    checkedAt: new Date().toISOString(),
    ...(env.K_REVISION !== undefined ? { revision: env.K_REVISION } : {}),
    region: env.GCP_REGION,
  };
}

export async function probeAll(): Promise<ProbeOutcome[]> {
  const env = getServerEnv();

  const web: ProbeOutcome = {
    kind: "reached",
    service: "web",
    report: localHealthReport(),
    latencyMs: 0,
  };

  // Parallel: two sequential 4s timeouts would make a fully-down manifest an
  const [physics, agent] = await Promise.all([
    probeService("physics", env.PHYSICS_SERVICE_URL),
    probeService("agent", env.AGENT_SERVICE_URL),
  ]);

  return [web, physics, agent];
}
