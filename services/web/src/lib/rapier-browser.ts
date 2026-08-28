/* The browser half of the parity claim. */

import type { SceneDescription, SimulationResult } from "@rinne/contracts";
import { MeshDecodeError, initScene, readPositions, simulateScene } from "@rinne/scene";

/* Same ceiling the server uses. A viewer should never fetch more than this. */
const MAX_MESH_BYTES = 32 * 1024 * 1024;
const MESH_TIMEOUT_MS = 30_000;

export type BrowserSimulationOutcome =
  | { readonly kind: "ok"; readonly result: SimulationResult }
  | { readonly kind: "failed"; readonly rule: string };

export function requestIdFromMeshUri(uri: string): string | null {
  const match =
    /^gs:\/\/[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]\/meshes\/([a-z0-9][a-z0-9-]{7,63})\.glb$/.exec(uri);
  return match?.[1] ?? null;
}

export async function fetchMeshBytes(requestId: string): Promise<Uint8Array | null> {
  const response = await fetch(`/api/mesh/${encodeURIComponent(requestId)}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(MESH_TIMEOUT_MS),
  });
  if (!response.ok) return null;

  const bytes = new Uint8Array(await response.arrayBuffer());
  return bytes.byteLength > MAX_MESH_BYTES ? null : bytes;
}

export async function simulateInBrowser(
  scene: SceneDescription,
): Promise<BrowserSimulationOutcome> {
  const requestId = requestIdFromMeshUri(scene.body.mesh.uri);
  if (requestId === null) return { kind: "failed", rule: "mesh uri is not one of ours" };

  const bytes = await fetchMeshBytes(requestId);
  if (bytes === null) return { kind: "failed", rule: "mesh could not be fetched" };

  // Idempotent, and the only await that differs from the server path.
  await initScene();

  try {
    return {
      kind: "ok",
      result: simulateScene(scene, readPositions(bytes), { runtime: "browser" }),
    };
  } catch (error) {
    if (error instanceof MeshDecodeError) return { kind: "failed", rule: error.rule };
    return { kind: "failed", rule: "simulation failed" };
  }
}
