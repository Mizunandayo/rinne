import { describe, expect, it } from "vitest";
import { agentJobSchema } from "../src/generated/schemas.js";
import { compileValidator, ContractViolationError } from "../src/validate.js";
import type { AgentJob, JobState } from "../src/generated/agent-job.js";

const assertJob = compileValidator<AgentJob>(agentJobSchema);

const source: AgentJob["source"] = {
  bucket: "rinne-scans-rinnehackathon",
  object: "scan-queue/desk.jpg",
  generation: "1756400000000000",
  contentType: "image/jpeg",
  sizeBytes: 482_113,
  receivedAt: "2026-08-29T04:20:00.000Z",
  eventId: "1234567890",
};

const queued: AgentJob = {
  schemaVersion: 1,
  jobId: "scan-9f2c41ab77d05e13",
  state: "queued",
  attempts: 1,
  createdAt: "2026-08-29T04:20:00.000Z",
  updatedAt: "2026-08-29T04:20:00.000Z",
  source,
  decisions: [
    {
      at: "2026-08-29T04:20:00.000Z",
      state: "queued",
      actor: "ingest",
      summary: "Storage event accepted; job created.",
    },
  ],
};

/**
 * The ten states of section 7, written out here rather than imported, so a
 * silent enum edit fails this test instead of passing it.
 */
const EXPECTED_STATES: readonly JobState[] = [
  "queued",
  "gated",
  "skipped_low_risk",
  "triaged",
  "simulating",
  "awaiting_verification",
  "refitting",
  "reporting",
  "done",
  "failed",
];

describe("AgentJob state set", () => {
  it("declares exactly the ten states of section 7, in order", () => {
    expect(agentJobSchema.definitions.jobState.enum).toEqual(EXPECTED_STATES);
  });

  it("keeps skipped_low_risk in the enum - it is an outcome, not a failure", () => {
    expect(agentJobSchema.definitions.jobState.enum).toContain("skipped_low_risk");
  });

  it("keeps gated in the enum even though the Gemma tier-0 gate was cut", () => {
    expect(agentJobSchema.definitions.jobState.enum).toContain("gated");
  });
});

describe("AgentJob", () => {
  it("accepts a freshly queued job", () => {
    expect(assertJob(queued)).toEqual(queued);
  });

  it("accepts a triaged job carrying the Flash decision", () => {
    const triaged: AgentJob = {
      ...queued,
      state: "triaged",
      updatedAt: "2026-08-29T04:20:03.000Z",
      triage: {
        review: true,
        shape: "tall-narrow",
        confidence: 0.95,
        rationale: "Tall narrow body over a small footprint; a lateral push is the risk.",
        model: "gemini-3.5-flash",
        basis: "flash-triage-v1",
        latencyMs: 1840,
        promptTokens: 1290,
        responseTokens: 92,
      },
      decisions: [
        ...queued.decisions,
        {
          at: "2026-08-29T04:20:03.000Z",
          state: "triaged",
          actor: "triage",
          summary: "Flash decided this warrants a physics review.",
          model: "gemini-3.5-flash",
          confidence: 0.95,
          latencyMs: 1840,
        },
      ],
    };
    expect(assertJob(triaged)).toEqual(triaged);
  });

  it("accepts a skipped_low_risk job - the most common outcome", () => {
    const skipped: AgentJob = {
      ...queued,
      state: "skipped_low_risk",
      triage: {
        review: false,
        shape: "flat-wide",
        confidence: 0.88,
        rationale: "Flat wide object resting on its largest face. Nothing to tip.",
        model: "gemini-3.5-flash",
        basis: "flash-triage-v1",
        latencyMs: 1502,
      },
    };
    expect(assertJob(skipped)).toEqual(skipped);
  });

  it("accepts a failed job carrying error and lastGoodState", () => {
    const failed: AgentJob = {
      ...queued,
      state: "failed",
      lastGoodState: "queued",
      error: {
        rule: "the scan object could not be read",
        at: "2026-08-29T04:20:02.000Z",
        retryable: true,
        actor: "ingest",
      },
    };
    expect(assertJob(failed)).toEqual(failed);
  });

  it("rejects a state that is not in the section 7 table", () => {
    expect(() => assertJob({ ...queued, state: "thinking" })).toThrow(ContractViolationError);
  });

  it("rejects an unknown property, so a typo cannot pass silently", () => {
    expect(() => assertJob({ ...queued, statee: "queued" })).toThrow(ContractViolationError);
  });

  it("rejects a jobId that could escape a collection or an object prefix", () => {
    for (const jobId of ["../secrets", "scan/../x", "Scan-9f2c41ab", "short"]) {
      expect(() => assertJob({ ...queued, jobId })).toThrow(ContractViolationError);
    }
  });

  it("rejects an attempts count above the section 12 loop cap", () => {
    expect(() => assertJob({ ...queued, attempts: 7 })).toThrow(ContractViolationError);
  });

  it("rejects a content type the reconstruction service would later refuse", () => {
    expect(() => assertJob({ ...queued, source: { ...source, contentType: "image/gif" } })).toThrow(
      ContractViolationError,
    );
  });

  it("rejects a non-numeric generation", () => {
    expect(() => assertJob({ ...queued, source: { ...source, generation: "latest" } })).toThrow(
      ContractViolationError,
    );
  });

  it("bounds the decision trail, so a redelivery storm cannot inflate a document", () => {
    const entry = queued.decisions[0]!;
    expect(() =>
      assertJob({ ...queued, decisions: Array.from({ length: 25 }, () => entry) }),
    ).toThrow(ContractViolationError);
  });

  it("rejects a triage record missing the model that produced it", () => {
    expect(() =>
      assertJob({
        ...queued,
        triage: {
          review: true,
          shape: "stack",
          confidence: 0.5,
          rationale: "A stack.",
          basis: "flash-triage-v1",
          latencyMs: 10,
        },
      }),
    ).toThrow(ContractViolationError);
  });
});
