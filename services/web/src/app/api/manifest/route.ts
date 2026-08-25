import { NextResponse } from "next/server";
import { getServerEnv } from "@/env";
import { probeAll, probeService } from "@/lib/health";

export const dynamic = "force-dynamic";

// A cold L4 needs most of its startup-probe budget before it answers.
const GPU_PROBE_TIMEOUT_MS = 120_000;

export async function GET(request: Request): Promise<NextResponse> {
  const url = new URL(request.url);
  const probeGpu = url.searchParams.get("probe") === "reconstruction";

  const outcomes = await probeAll();

  const resolved = probeGpu
    ? await Promise.all(
        outcomes.map(async (outcome) =>
          outcome.kind === "cold"
            ? probeService(
                "reconstruction",
                getServerEnv().RECONSTRUCTION_SERVICE_URL,
                GPU_PROBE_TIMEOUT_MS,
              )
            : outcome,
        ),
      )
    : outcomes;

  // A cold service is neither healthy nor broken, so it does not count against
  const rated = resolved.filter((outcome) => outcome.kind !== "cold");
  const allOk = rated.every((o) => o.kind === "reached" && o.report.status === "ok");

  return NextResponse.json(
    {
      allOk,
      checkedAt: new Date().toISOString(),
      services: resolved.map((o) => {
        if (o.kind === "cold") {
          return { service: o.service, reachable: false, status: "cold", probed: false };
        }
        if (o.kind === "reached") {
          return {
            service: o.service,
            reachable: true,
            status: o.report.status,
            version: o.report.version,
            revision: o.report.revision ?? null,
            region: o.report.region ?? null,
            detail: o.report.detail ?? null,
            latencyMs: o.latencyMs,
            probed: true,
          };
        }
        return {
          service: o.service,
          reachable: false,
          status: "down",
          reason: o.reason,
          latencyMs: o.latencyMs,
          probed: true,
        };
      }),
    },
    {
      status: allOk ? 200 : 503,
      headers: { "cache-control": "no-store, max-age=0" },
    },
  );
}
