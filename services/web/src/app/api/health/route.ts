import { NextResponse } from "next/server";
import { localHealthReport } from "@/lib/health";


export const dynamic = "force-dynamic";


export function GET(): NextResponse {
  return NextResponse.json(localHealthReport(), {
    headers: { "cache-control": "no-store, max-age=0" },
  });
}