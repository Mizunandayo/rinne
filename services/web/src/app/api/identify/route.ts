import { NextResponse } from "next/server";
import { getServerEnv } from "@/env";
import { getIdToken } from "@/lib/gcp-auth";

/* Proxies one image to the agent's identification step. The agent is IAM-private,
   so the browser can never reach it directly; this route is the only path, and it
   forwards nothing but the image. */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_UPLOAD_BYTES = 6_291_456;
const TIMEOUT_MS = 60_000;

export async function POST(request: Request): Promise<NextResponse> {
  const env = getServerEnv();

  const form = await request.formData();
  const image = form.get("image");
  if (!(image instanceof File)) {
    return NextResponse.json({ error: "one image part is required" }, { status: 400 });
  }
  if (image.size > MAX_UPLOAD_BYTES) {
    return NextResponse.json({ error: "the image exceeds the size limit" }, { status: 413 });
  }

  const token = await getIdToken(env.AGENT_SERVICE_URL);
  if (token === null) {
    return NextResponse.json({ error: "identification is unavailable" }, { status: 503 });
  }

  const forwarded = new FormData();
  forwarded.append("image", image, image.name);

  try {
    const response = await fetch(new URL("/v1/identify", env.AGENT_SERVICE_URL), {
      method: "POST",
      body: forwarded,
      cache: "no-store",
      redirect: "error",
      headers: { authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });

    const text = await response.text();
    if (!response.ok) {
      // Upstream auth problems are ours, not the caller's.
      const status = response.status === 401 || response.status === 403 ? 502 : response.status;
      return NextResponse.json({ error: "identification failed" }, { status });
    }
    return new NextResponse(text, {
      status: 200,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch {
    return NextResponse.json({ error: "identification is unavailable" }, { status: 503 });
  }
}
