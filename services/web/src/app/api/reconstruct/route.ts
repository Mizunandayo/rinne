import { NextResponse } from "next/server";
import { checkRateLimit } from "@/lib/rate-limit";
import { callReconstruction } from "@/lib/reconstruction";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

const MAX_IMAGES = 4;

function fail(status: number, error: string, extra?: HeadersInit): NextResponse {
  return NextResponse.json(
    { error },
    { status, headers: { "cache-control": "no-store", ...extra } },
  );
}

export async function POST(request: Request): Promise<NextResponse> {
  // Rate limit BEFORE reading the body.
  const limit = checkRateLimit(request.headers);
  if (!limit.allowed) {
    return fail(429, limit.kind === "global" ? "Service is busy" : "Too many scans", {
      "retry-after": String(limit.retryAfterSeconds),
    });
  }

  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().trimStart().startsWith("multipart/form-data")) {
    return fail(415, "Request must be multipart/form-data");
  }

  let incoming: FormData;
  try {
    incoming = await request.formData();
  } catch {
    return fail(400, "Request is not valid multipart/form-data");
  }

  const document = incoming.get("request");
  if (typeof document !== "string") {
    return fail(400, "Request part is missing or is not text");
  }

  const images = incoming.getAll("images").filter((value): value is File => value instanceof File);
  if (images.length === 0) return fail(400, "At least one image is required");
  if (images.length > MAX_IMAGES) return fail(400, "Too many images");

  // Rebuilt, not piped: only these two field names cross the boundary.
  const outgoing = new FormData();
  outgoing.append("request", document);
  for (const image of images) outgoing.append("images", image, image.name);

  const outcome = await callReconstruction(outgoing);

  if (outcome.kind === "rejected") return fail(outcome.status, outcome.error);
  if (outcome.kind === "unavailable") return fail(503, outcome.error);

  return NextResponse.json(outcome.result, { headers: { "cache-control": "no-store" } });
}
