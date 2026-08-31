import "server-only";
import {
  compileValidator,
  ContractViolationError,
  reconstructionResultSchema,
  type ReconstructionResult,
} from "@rinne/contracts";
import { getServerEnv } from "../env";
import { getIdToken } from "./gcp-auth";

const assertResult = compileValidator<ReconstructionResult>(reconstructionResultSchema);
const MAX_UPLOAD_BYTES = 26_214_400;
const MAX_RESPONSE_BYTES = 256 * 1024;

export type ReconstructOutcome =
  | { readonly kind: "ok"; readonly result: ReconstructionResult }
  | { readonly kind: "rejected"; readonly status: number; readonly error: string }
  | { readonly kind: "unavailable"; readonly error: string };

interface ErrorEnvelope {
  readonly error?: unknown;
}

/* Forward a multipart body to the GPU service with an audeience-scoped ID token.*/
export async function callReconstruction(form: FormData): Promise<ReconstructOutcome> {
  const env = getServerEnv();
  const token = await getIdToken(env.RECONSTRUCTION_SERVICE_URL);

  if (token === null) {
    return { kind: "unavailable", error: "Reconstruction service is unreachable" };
  }

  let declaredBytes = 0;
  for (const value of form.values()) {
    if (value instanceof File) declaredBytes += value.size;
  }
  if (declaredBytes > MAX_UPLOAD_BYTES) {
    return { kind: "rejected", status: 413, error: "Upload exceeds the size limit" };
  }

  try {
    const response = await fetch(new URL("/v1/reconstruct", env.RECONSTRUCTION_SERVICE_URL), {
      method: "POST",
      body: form,
      cache: "no-store",
      redirect: "error",
      headers: { authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(env.RECONSTRUCT_TIMEOUT_MS),
    });

    const text = await response.text();
    if (text.length > MAX_RESPONSE_BYTES) {
      return { kind: "unavailable", error: "Reconstruction returned an oversized response" };
    }

    if (!response.ok) {
      // Pass the service's RULE through unchanged - it is already written to be
      // safe for a caller, and rewording it here would lose the diagnosis.
      const envelope = safeParse(text);
      const error = typeof envelope?.error === "string" ? envelope.error : "Reconstruction failed";
      // Upstream auth problems are ours, not the caller's.
      const status = response.status === 401 || response.status === 403 ? 502 : response.status;
      return { kind: "rejected", status, error };
    }

    // Validate on the way IN. The GPU service is ours, but a contract violation
    // is exactly the thing that must not reach a viewer as a broken mesh.
    return { kind: "ok", result: assertResult(safeParse(text)) };
  } catch (error) {
    // A contract violation is NOT a network failure, and calling it one sent three
    // rounds of debugging at the network. It means this build and the service
    // disagree about the schema - usually one of them was deployed and the other
    // was not - so the log has to name the mismatch.
    if (error instanceof ContractViolationError) {
      console.error(
        JSON.stringify({
          severity: "ERROR",
          message: "reconstruction returned a result this build cannot validate",
          reason: "contract-mismatch",
          detail: error.message,
        }),
      );
      return {
        kind: "unavailable",
        error: "Reconstruction returned a result this build does not recognise",
      };
    }

    const timedOut = error instanceof Error && error.name === "TimeoutError";
    console.error(
      JSON.stringify({
        severity: "ERROR",
        message: "reconstruction call failed",
        reason: timedOut ? "timeout" : "unreachable",
      }),
    );
    return {
      kind: "unavailable",
      error: timedOut ? "Reconstruction timed out" : "Reconstruction service is unreachable",
    };
  }
}

function safeParse(text: string): (ErrorEnvelope & Record<string, unknown>) | null {
  try {
    return JSON.parse(text) as ErrorEnvelope & Record<string, unknown>;
  } catch {
    return null;
  }
}
