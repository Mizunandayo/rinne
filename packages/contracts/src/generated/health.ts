/* eslint-disable */
/**
 * GENERATED FILE — DO NOT EDIT BY HAND.
 *
 * Source of truth : packages/contracts/schemas
 * Regenerate      : pnpm --filter @rinne/contracts run generate:ts
 *
 * CI runs the same generator with --check and fails the build if this file
 * differs. A schema edit without a regeneration is a build failure, which is
 * the entire point of defining the contract once.
 */

/**
 * Uniform liveness and readiness payload returned by every Rinne service. The web service's manifest page renders this, and smoke-test.ps1 asserts against it, so the shape is a contract and not a convenience.
 */
export interface HealthReport {
  /**
   * Which Rinne service produced this report.
   */
  service: "web" | "physics" | "agent" | "reconstruction";
  /**
   * ok: fully serving. degraded: serving with a failed non-critical dependency. down: not serving.
   */
  status: "ok" | "degraded" | "down";
  /**
   * Build identifier. Set from the image tag at deploy time.
   */
  version: string;
  /**
   * RFC 3339 timestamp of this check, produced at request time and never cached.
   */
  checkedAt: string;
  /**
   * Cloud Run revision name, from the K_REVISION environment variable.
   */
  revision?: string;
  /**
   * Deployment region, for confirming the asia-southeast1 decision holds in production.
   */
  region?: string;
  /**
   * Short operator-facing note. Never contains a stack trace, an internal hostname, or a credential.
   */
  detail?: string;
  /**
   * Downstream checks this service performed. Bounded so a compromised or buggy downstream cannot inflate a response.
   *
   * @maxItems 16
   */
  dependencies?:
    | []
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ]
    | [
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
        {
          name: string;
          status: "ok" | "degraded" | "down";
          latencyMs?: number;
          detail?: string;
        },
      ];
}
