/* An OAuth access token for the GCS JSON API, readonly. */

const METADATA_TOKEN_URL =
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token";
/* Readonly this service reads meshes and never writes one */
const STORAGE_READ_SCOPE = "https://www.googleapis.com/auth/devstorage.read_only";
const METADATA_TIMEOUT_MS = 3000;
const REFRESH_SKEW_SECONDS = 120;

interface CachedToken {
  readonly token: string;
  readonly expiresAtMs: number;
}

let cached: CachedToken | null = null;

export interface TokenSource {
  readonly developmentToken?: string | undefined;
  readonly onCloudRun: boolean;
}

export async function getAccessToken(source: TokenSource): Promise<string | null> {
  if (!source.onCloudRun) {
    const token = source.developmentToken ?? "";
    return token.length > 0 ? token : null;
  }

  const now = Date.now();
  if (cached !== null && cached.expiresAtMs - REFRESH_SKEW_SECONDS * 1000 > now) {
    return cached.token;
  }

  try {
    const response = await fetch(
      `${METADATA_TOKEN_URL}?scopes=${encodeURIComponent(STORAGE_READ_SCOPE)}`,
      {
        headers: { "Metadata-Flavor": "Google" },
        redirect: "error",
        signal: AbortSignal.timeout(METADATA_TIMEOUT_MS),
      },
    );
    if (!response.ok) return null;

    const payload: unknown = await response.json();
    if (typeof payload !== "object" || payload === null) return null;
    const { access_token: token, expires_in: expiresIn } = payload as {
      access_token?: unknown;
      expires_in?: unknown;
    };
    if (typeof token !== "string" || token.length === 0) return null;

    const lifetime = typeof expiresIn === "number" && Number.isFinite(expiresIn) ? expiresIn : 3600;
    cached = { token, expiresAtMs: now + lifetime * 1000 };
    return token;
  } catch {
    return null;
  }
}

/** Test seam. */
export function clearAccessTokenCache(): void {
  cached = null;
}
