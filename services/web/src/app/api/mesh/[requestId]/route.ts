import { NextResponse } from "next/server";
import { fetchMesh, GLB_CONTENT_TYPE, isValidRequestId } from "@/lib/gcs";

export const dynamic = "force-dynamic";

interface RouteContext {
  readonly params: Promise<{ readonly requestId: string }>;
}

export async function GET(_request: Request, context: RouteContext): Promise<NextResponse> {
  const { requestId } = await context.params;

  if (!isValidRequestId(requestId)) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const outcome = await fetchMesh(requestId);

  switch (outcome.kind) {
    case "ok":
      return new NextResponse(outcome.bytes, {
        headers: {
          "content-type": GLB_CONTENT_TYPE,
          "content-length": String(outcome.bytes.byteLength),
          // Immutable: ifGenerationMatch=0 means a requestId is written once.
          "cache-control": "private, max-age=3600, immutable",
          "content-disposition": `inline; filename="${requestId}.glb"`,
        },
      }) as NextResponse;
    case "not-found":
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    case "too-large":
      return NextResponse.json({ error: "Mesh is too large to serve" }, { status: 502 });
    case "unauthorized":
    case "unavailable":
      return NextResponse.json({ error: "Mesh is unavailable" }, { status: 502 });
  }
}
