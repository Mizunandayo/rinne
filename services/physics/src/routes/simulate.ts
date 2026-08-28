import type { FastifyInstance, FastifyPluginAsync } from "fastify";
import {
  sceneDescriptionSchema,
  simulationResultSchema,
  toRouteSchema,
  type SceneDescription,
  type SimulationResult,
} from "@rinne/contracts";
import { MeshDecodeError, readPositions, simulateScene } from "@rinne/scene";
import type { MeshFetcher } from "../physics/mesh-fetch.js";

/** Errors name the RULE. The envelope matches every other Rinne service. */
interface Refusal {
  readonly status: number;
  readonly error: string;
}

const MESH_REFUSALS: Record<string, Refusal> = {
  "not-found": { status: 404, error: "mesh not found" },
  unauthorized: { status: 502, error: "storage refused the mesh read" },
  unavailable: { status: 503, error: "storage is unavailable" },
};

export function simulateRoutes(fetchMesh: MeshFetcher): FastifyPluginAsync {
  const bodySchema = toRouteSchema(sceneDescriptionSchema);
  const responseSchema = toRouteSchema(simulationResultSchema);

  // eslint-disable-next-line @typescript-eslint/require-await
  return async (app: FastifyInstance): Promise<void> => {
    app.post<{ Body: SceneDescription }>(
      "/v1/simulate",
      {
        schema: { body: bodySchema, response: { 200: responseSchema } },
      },
      async (request, reply): Promise<SimulationResult | { error: string; requestId: string }> => {
        const scene = request.body;

        const mesh = await fetchMesh(scene.body.mesh.uri);
        if (mesh.kind === "rejected") {
          void reply.code(400);
          return { error: mesh.rule, requestId: request.id };
        }
        if (mesh.kind !== "ok") {
          const refusal = MESH_REFUSALS[mesh.kind] ?? MESH_REFUSALS["unavailable"];
          void reply.code(refusal?.status ?? 503);
          return { error: refusal?.error ?? "storage is unavailable", requestId: request.id };
        }

        let points: Float32Array;
        try {
          points = readPositions(mesh.bytes);
        } catch (error) {
          if (error instanceof MeshDecodeError) {
            void reply.code(422);
            return { error: error.rule, requestId: request.id };
          }
          throw error;
        }

        return simulateScene(scene, points, { runtime: "node" });
      },
    );
  };
}
