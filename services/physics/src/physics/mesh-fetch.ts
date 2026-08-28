import { getAccessToken, type TokenSource } from "../lib/gcp-auth.js";

const STORAGE_ROOT = "https://storage.googleapis.com/storage/v1/b";

export type MeshFetchOutcome =
  | { readonly kind: "ok"; readonly bytes: Uint8Array }
  | { readonly kind: "rejected"; readonly rule: string }
  | { readonly kind: "not-found" }
  | { readonly kind: "unauthorized" }
  | { readonly kind: "unavailable" };

export type MeshFetcher = (uri: string) => Promise<MeshFetchOutcome>;

export interface ParsedGsUri {
  readonly bucket: string;
  readonly object: string;
}

const GS_URI = /^gs:\/\/([a-z0-9][a-z0-9._-]{1,61}[a-z0-9])\/(.{1,512})$/;

export function parseGsUri(uri: string): ParsedGsUri | null {
  const match = GS_URI.exec(uri);
  if (match === null) return null;
  const bucket = match[1];
  const object = match[2];
  if (bucket === undefined || object === undefined) return null;
  if (object.includes("..") || object.startsWith("/")) return null;
  return { bucket, object };
}

export interface MeshFetchConfig {
  readonly bucket: string;
  readonly maxBytes: number;
  readonly timeoutMs: number;
  readonly tokenSource: TokenSource;
}

export function createMeshFetcher(config: MeshFetchConfig): MeshFetcher {
  return async (uri: string): Promise<MeshFetchOutcome> => {
    const parsed = parseGsUri(uri);
    if (parsed === null) return { kind: "rejected", rule: "mesh uri is not a valid gs:// uri" };
    if (parsed.bucket !== config.bucket) {
      return { kind: "rejected", rule: "mesh uri points outside the artifacts bucket" };
    }

    const token = await getAccessToken(config.tokenSource);
    if (token === null) return { kind: "unauthorized" };

    const url =
      `${STORAGE_ROOT}/${encodeURIComponent(parsed.bucket)}` +
      `/o/${encodeURIComponent(parsed.object)}?alt=media`;

    try {
      const response = await fetch(url, {
        headers: { authorization: `Bearer ${token}` },
        redirect: "error",
        signal: AbortSignal.timeout(config.timeoutMs),
      });

      if (response.status === 404) return { kind: "not-found" };
      if (response.status === 401 || response.status === 403) return { kind: "unauthorized" };
      if (!response.ok) return { kind: "unavailable" };

      const declared = Number(response.headers.get("content-length") ?? "0");
      if (declared > config.maxBytes) {
        return { kind: "rejected", rule: "mesh exceeds the size limit" };
      }

      const bytes = new Uint8Array(await response.arrayBuffer());
      if (bytes.byteLength > config.maxBytes) {
        return { kind: "rejected", rule: "mesh exceeds the size limit" };
      }
      return { kind: "ok", bytes };
    } catch {
      return { kind: "unavailable" };
    }
  };
}
