import { describe, expect, it } from "vitest";
import { createMeshFetcher, parseGsUri } from "../src/physics/mesh-fetch.js";

const BUCKET = "rinne-artifacts-rinnehackathon";

describe("parseGsUri", () => {
  it("splits a well-formed uri", () => {
    expect(parseGsUri(`gs://${BUCKET}/meshes/scan-000001.glb`)).toEqual({
      bucket: BUCKET,
      object: "meshes/scan-000001.glb",
    });
  });

  it("REFUSES anything that is not gs://", () => {
    for (const uri of [
      "http://metadata.google.internal/computeMetadata/v1/",
      "https://storage.googleapis.com/x/y",
      "file:///etc/passwd",
      "gs://",
      "gs://bucket",
    ]) {
      expect(parseGsUri(uri), uri).toBeNull();
    }
  });

  it("refuses a traversal segment rather than trusting normalisation", () => {
    expect(parseGsUri(`gs://${BUCKET}/meshes/../../secret.glb`)).toBeNull();
    expect(parseGsUri(`gs://${BUCKET}//etc/passwd`)).toBeNull();
  });
});

describe("createMeshFetcher", () => {
  const fetcher = createMeshFetcher({
    bucket: BUCKET,
    maxBytes: 1024,
    timeoutMs: 1000,
    tokenSource: { onCloudRun: false, developmentToken: "dev-token" },
  });

  it("REFUSES a bucket that is not ours, which the schema cannot express", () => {
    return expect(fetcher("gs://someone-elses-bucket/meshes/x.glb")).resolves.toEqual({
      kind: "rejected",
      rule: "mesh uri points outside the artifacts bucket",
    });
  });

  it("refuses a malformed uri before it ever mints a token", () => {
    return expect(fetcher("http://metadata.google.internal/")).resolves.toEqual({
      kind: "rejected",
      rule: "mesh uri is not a valid gs:// uri",
    });
  });

  it("reports unauthorized when no token is available", () => {
    const tokenless = createMeshFetcher({
      bucket: BUCKET,
      maxBytes: 1024,
      timeoutMs: 1000,
      tokenSource: { onCloudRun: false, developmentToken: "" },
    });
    return expect(tokenless(`gs://${BUCKET}/meshes/x.glb`)).resolves.toEqual({
      kind: "unauthorized",
    });
  });
});
