import "server-only";
import { getServerEnv } from "../env";
import { getAccessToken } from "./gcp-auth";

const STORAGE_ROOT = "https://storage.googleapis.com/storage/v1/b";

// A stub GLB is ~350KB and a TripoSR one is a few MB. This is the ceiling the
// route streams under, well below what a browser viewer should ever fetch.
const MAX_MESH_BYTES = 32 * 1024 * 1024;

export const GLB_CONTENT_TYPE = "model/gltf-binary";

export type MeshFetchOutcome =
  | { readonly kind: "ok"; readonly bytes: ArrayBuffer }
  | { readonly kind: "not-found" }
  | { readonly kind: "too-large" }
  | { readonly kind: "unauthorized" }
  | { readonly kind: "unavailable" };

const REQUEST_ID = /^[a-z0-9][a-z0-9-]{7,63}$/;

export function isValidRequestId(value: string): boolean {
  return REQUEST_ID.test(value);
}

export function meshObjectName(requestId: string): string {
  return `meshes/${requestId}.glb`;
}

export async function fetchMesh(requestId: string): Promise<MeshFetchOutcome> {
  if (!isValidRequestId(requestId)) return { kind: "not-found" };

  const env = getServerEnv();
  const token = await getAccessToken();
  if (token === null) return { kind: "unauthorized" };

  const object = encodeURIComponent(meshObjectName(requestId));
  const url = `${STORAGE_ROOT}/${encodeURIComponent(env.GCS_ARTIFACTS_BUCKET)}/o/${object}?alt=media`;

  try {
    const response = await fetch(url, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
      // Following a redirect from a storage endpoint would make this an SSRF
      // primitive holding a live credential.
      redirect: "error",
      signal: AbortSignal.timeout(30_000),
    });

    if (response.status === 404) return { kind: "not-found" };
    if (response.status === 401 || response.status === 403) return { kind: "unauthorized" };
    if (!response.ok) return { kind: "unavailable" };

    const declared = Number(response.headers.get("content-length") ?? "0");
    if (declared > MAX_MESH_BYTES) return { kind: "too-large" };

    const bytes = await response.arrayBuffer();
    if (bytes.byteLength > MAX_MESH_BYTES) return { kind: "too-large" };

    return { kind: "ok", bytes };
  } catch {
    console.error(JSON.stringify({ severity: "ERROR", message: "mesh fetch failed", requestId }));
    return { kind: "unavailable" };
  }
}

/** gs://bucket/meshes/{id}.glb -> the id, or null if it is not ours. */
export function requestIdFromUri(uri: string): string | null {
  const env = getServerEnv();
  const prefix = `gs://${env.GCS_ARTIFACTS_BUCKET}/meshes/`;
  if (!uri.startsWith(prefix) || !uri.endsWith(".glb")) return null;
  const id = uri.slice(prefix.length, -".glb".length);
  return isValidRequestId(id) ? id : null;
}
