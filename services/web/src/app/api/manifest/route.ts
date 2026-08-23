import { NextResponse } from "next/server";
import { probeAll } from "@/lib/health";


export const dynamic = "force-dynamic"



export async function GET(): Promise<NextResponse> {
  const outcomes = await probeAll();
  const allOk = outcomes.every((o) => o.kind === "reached" && o.report.status === "ok");

  return NextResponse.json(
    {
      allOk,
      checkedAt: new Date().toISOString(),
      services: outcomes.map((o) =>
        o.kind === "reached"
          ? {
              service: o.service,
              reachable: true,
              status: o.report.status,
              version: o.report.version,
              revision: o.report.revision ?? null,
              region: o.report.region ?? null,
              latencyMs: o.latencyMs,
            }
          : {
              service: o.service,
              reachable: false,
              status: "down",
              reason: o.reason,
              latencyMs: o.latencyMs,
            },
      ),
    },
    {
      status: allOk ? 200 : 503,
      headers: { "cache-control": "no-store, max-age=0" },
    },
  );
}