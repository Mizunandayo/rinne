import "server-only";
import { getServerEnv, isCloudRun } from "../env";

const METADATA_ROOT = "http://metadata.google.internal/computeMetadata/v1";
const METADATA_IDENTITY_URL = `${METADATA_ROOT}/instance/service-accounts/default/identity`;
const METADATA_TOKEN_URL = `${METADATA_ROOT}/instance/service-accounts/default/token`;

/** Read-only. This service reads meshes and never writes one. */
const STORAGE_READ_SCOPE = "https://www.googleapis.com/auth/devstorage.read_only";

const METADATA_TIMEOUT_MS = 3000;
const REFRESH_SKEW_SECONDS = 120;

interface CachedToken {
  readonly token: string;
  readonly expiresAtMs: number;
}

const cache = new Map<string, CachedToken>();

function readExpiry(token: string): number | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const payloadSegment = parts[1];
  if (payloadSegment === undefined) return null;

  try {
    const json = Buffer.from(payloadSegment, "base64url").toString("utf8");
    const payload: unknown = JSON.parse(json);
    if (typeof payload === "object" && payload !== null && "exp" in payload) {
      const exp = (payload as { exp: unknown }).exp;
      if (typeof exp === "number" && Number.isFinite(exp)) return exp * 1000;
    }
  } catch {
    return null;
  }
  return null;
}

/**
 * @param audience The full target service URL, e.g. https://rinne-physics-...run.app
 *                 Cloud Run rejects a token whose audience does not match.
 * @returns The token, or null when no identity is available (local development).
 */
export async function getIdToken(audience: string): Promise<string | null> {
  const env = getServerEnv();

  if (!isCloudRun()) {
    // Local development: populate RINNE_DEV_ID_TOKEN from
    return env.RINNE_DEV_ID_TOKEN && env.RINNE_DEV_ID_TOKEN.length > 0
      ? env.RINNE_DEV_ID_TOKEN
      : null;
  }

  const now = Date.now();
  const hit = cache.get(audience);
  if (hit && hit.expiresAtMs - REFRESH_SKEW_SECONDS * 1000 > now) {
    return hit.token;
  }

  try {
    const url = `${METADATA_IDENTITY_URL}?audience=${encodeURIComponent(audience)}&format=full`;
    const response = await fetch(url, {
      headers: { "Metadata-Flavor": "Google" },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(METADATA_TIMEOUT_MS),
    });

    if (!response.ok) {
      // Status only. The body of a failed metadata call can echo request detail.
      console.error(
        JSON.stringify({
          severity: "ERROR",
          message: "metadata server refused an identity token",
          status: response.status,
        }),
      );
      return null;
    }

    const token = (await response.text()).trim();
    if (token.length === 0) return null;

    const expiresAtMs = readExpiry(token) ?? now + 45 * 60 * 1000;
    cache.set(audience, { token, expiresAtMs });
    return token;
  } catch {
    console.error(JSON.stringify({ severity: "ERROR", message: "metadata server unreachable" }));
    return null;
  }
}

interface CachedAccess {
  readonly token: string;
  readonly expiresAtMs: number;
}

let accessToken: CachedAccess | null = null;

/**
 * OAuth access token for the GCS JSON API, scoped to read-only.
 *
 * Separate from getIdToken: an ID token authenticates to Cloud Run, an access
 * token authorises a Google API. They are not interchangeable.
 */
export async function getAccessToken(): Promise<string | null> {
  const env = getServerEnv();

  if (!isCloudRun()) {
    return env.RINNE_DEV_ACCESS_TOKEN && env.RINNE_DEV_ACCESS_TOKEN.length > 0
      ? env.RINNE_DEV_ACCESS_TOKEN
      : null;
  }

  const now = Date.now();
  if (accessToken && accessToken.expiresAtMs - REFRESH_SKEW_SECONDS * 1000 > now) {
    return accessToken.token;
  }

  try {
    const url = `${METADATA_TOKEN_URL}?scopes=${encodeURIComponent(STORAGE_READ_SCOPE)}`;
    const response = await fetch(url, {
      headers: { "Metadata-Flavor": "Google" },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(METADATA_TIMEOUT_MS),
    });

    if (!response.ok) {
      console.error(
        JSON.stringify({
          severity: "ERROR",
          message: "metadata server refused an access token",
          status: response.status,
        }),
      );
      return null;
    }

    const payload: unknown = await response.json();
    if (typeof payload !== "object" || payload === null) return null;
    const { access_token: token, expires_in: expiresIn } = payload as {
      access_token?: unknown;
      expires_in?: unknown;
    };
    if (typeof token !== "string" || token.length === 0) return null;

    const lifetime = typeof expiresIn === "number" && Number.isFinite(expiresIn) ? expiresIn : 3600;
    accessToken = { token, expiresAtMs: now + lifetime * 1000 };
    return token;
  } catch {
    console.error(JSON.stringify({ severity: "ERROR", message: "metadata server unreachable" }));
    return null;
  }
}

/** Test seam. */
export function clearIdTokenCache(): void {
  cache.clear();
  accessToken = null;
}
