import "server-only";
import { getServerEnv } from "../env";

export type LimitKind = "ip" | "global";

export interface LimitDecision {
  readonly allowed: boolean;
  readonly kind: LimitKind | null;
  readonly retryAfterSeconds: number;
}

interface Window {
  count: number;
  resetAtMs: number;
}

const windows = new Map<string, Window>();

const MAX_TRACKED_KEYS = 1024;
const GLOBAL_KEY = "__global__";

/* Client address from X-Forwarded-For, taking the LAST entry.*/
export function clientAddress(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for");
  if (forwarded) {
    const parts = forwarded
      .split(",")
      .map((part) => part.trim())
      .filter((part) => part.length > 0);
    const last = parts[parts.length - 1];
    if (last !== undefined) return last;
  }
  return "unknown";
}

function hit(key: string, limit: number, windowMs: number, now: number): boolean {
  const existing = windows.get(key);

  if (existing === undefined || existing.resetAtMs <= now) {
    if (windows.size >= MAX_TRACKED_KEYS) sweep(now);
    windows.set(key, { count: 1, resetAtMs: now + windowMs });
    return true;
  }

  if (existing.count >= limit) return false;
  existing.count += 1;
  return true;
}

function sweep(now: number): void {
  for (const [key, window] of windows) {
    if (window.resetAtMs <= now) windows.delete(key);
  }
  // Still full of live windows: drop the oldest rather than grow unbounded.
  if (windows.size >= MAX_TRACKED_KEYS) {
    const oldest = [...windows.entries()].sort((a, b) => a[1].resetAtMs - b[1].resetAtMs);
    for (const [key] of oldest.slice(0, Math.floor(MAX_TRACKED_KEYS / 4))) windows.delete(key);
  }
}

function retryAfter(key: string, now: number): number {
  const window = windows.get(key);
  if (window === undefined) return 1;
  return Math.max(1, Math.ceil((window.resetAtMs - now) / 1000));
}

/**
 * Global cap is checked FIRST and only consumed once the per-IP cap passes, so
 * one address cannot burn the shared budget by hammering its own limit.
 */
export function checkRateLimit(headers: Headers, now = Date.now()): LimitDecision {
  const env = getServerEnv();
  const address = clientAddress(headers);

  if (!hit(`ip:${address}`, env.RATE_LIMIT_PER_IP, env.RATE_LIMIT_WINDOW_MS, now)) {
    return { allowed: false, kind: "ip", retryAfterSeconds: retryAfter(`ip:${address}`, now) };
  }

  if (!hit(GLOBAL_KEY, env.RATE_LIMIT_GLOBAL, env.RATE_LIMIT_WINDOW_MS, now)) {
    return { allowed: false, kind: "global", retryAfterSeconds: retryAfter(GLOBAL_KEY, now) };
  }

  return { allowed: true, kind: null, retryAfterSeconds: 0 };
}

/** Test seam. */
export function resetRateLimits(): void {
  windows.clear();
}
