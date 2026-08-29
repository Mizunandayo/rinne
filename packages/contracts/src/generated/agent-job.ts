/* eslint-disable */
/**
 * GENERATED FILE — DO NOT EDIT BY HAND.
 *
 * Source of truth : packages/contracts/schemas
 * Regenerate      : pnpm --filter @rinne/contracts run generate:ts
 *
 * CI runs the same generator with --check and fails the build if this file
 * differs. A schema edit without a regeneration is a build failure, which is
 * the entire point of defining the contract once.
 */

/**
 * The exhaustive state set from section 7. skipped_low_risk is a LEGITIMATE terminal outcome and the most common one - triage deciding no review is needed is the product working, not failing. gated is designed and NOT shipped: the Gemma tier-0 gate was cut on Aug 28, so nothing in this build emits it; it stays in the enum so the three-tier cascade remains describable and the cut remains visible. failed is reachable from every non-terminal state and carries error and lastGoodState.
 */
export type JobState =
  | "queued"
  | "gated"
  | "skipped_low_risk"
  | "triaged"
  | "simulating"
  | "awaiting_verification"
  | "refitting"
  | "reporting"
  | "done"
  | "failed";
/**
 * Which step of the loop acted. Closed so the dashboard can group by it, and so a step that does not exist yet cannot appear in a log without a schema change.
 */
export type JobActor =
  | "ingest"
  | "triage"
  | "gate"
  | "reconstruction"
  | "physics"
  | "refit"
  | "report"
  | "operator";

/**
 * One scan, one Firestore document, one exhaustive state machine. This is the decision log section 7 promises, and the only place a job's state lives - there is no in-process table it could disagree with. It is a shared contract rather than a private shape because the cockpit reads it from TypeScript, and because generating the ten states into both languages is what turns "no implicit states" into a build gate instead of a discipline.
 */
export interface AgentJob {
  /**
   * Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.
   */
  schemaVersion: 1;
  /**
   * Firestore document key, and later the reconstruction requestId and the sceneId. Derived deterministically from bucket, object and generation so a redelivered event maps to the same document instead of a second job. Same pattern as requestId and sceneId, for the same reason: no slash, no dot, no traversal.
   */
  jobId: string;
  state: JobState;
  lastGoodState?: JobState;
  /**
   * How many times the agent has begun work on this job. Section 12 forbids unbounded loops; this is where that rule is enforced for the agent path, and the ceiling of 6 matches the tool-loop cap and SceneDescription.provenance.refitIteration.
   */
  attempts: number;
  /**
   * RFC 3339 timestamp of the delivery that created this document.
   */
  createdAt: string;
  /**
   * RFC 3339 timestamp of the last accepted transition.
   */
  updatedAt: string;
  source: ScanSource;
  triage?: TriageRecord;
  error?: JobError;
  /**
   * Append-only audit trail. Bounded so a redelivery storm or a buggy loop cannot inflate a document, and because Firestore charges by document size.
   *
   * @maxItems 24
   */
  decisions: DecisionEntry[];
}
/**
 * The object that triggered this job, as reported by the storage event. Recorded in full so the decision log is reproducible from the document alone - a judge can re-run the exact object the agent saw.
 */
export interface ScanSource {
  /**
   * Checked against one configured bucket before any work happens. The delivery is authenticated by IAM, but the bucket name inside it is still payload.
   */
  bucket: string;
  object: string;
  /**
   * GCS reports generation as a decimal string, and it stays a string here for the same reason: it is an int64 identifier, not a number anything does arithmetic on. It is part of the jobId derivation, so overwriting an object produces a new job rather than silently reusing the old one.
   */
  generation: string;
  /**
   * Allowlisted before the object is read. The same three types the reconstruction service accepts, so a scan that triages cannot then be refused downstream.
   */
  contentType: "image/jpeg" | "image/png" | "image/webp";
  sizeBytes: number;
  receivedAt: string;
  /**
   * CloudEvent id of the delivery that created the job. Two deliveries of one object carry the same id; a genuine re-upload does not. Evidence, not a control - the control is the create-only write.
   */
  eventId?: string;
}
/**
 * Section 7 step 1. The judgment a script cannot make: is this object worth a physics review at all. shape is the classification the decision rested on, and it is the input Day 5's test selection reads - recording it here means selection does not have to look at the image a second time.
 */
export interface TriageRecord {
  /**
   * true: this warrants a physics review, and the job moves to triaged. false: it does not, and the job terminates in skipped_low_risk.
   */
  review: boolean;
  /**
   * What the model saw. no-object is the case the cut Gemma tier-0 gate would have caught more cheaply; Flash catches it now, which is the cost argument for that gate written down as a value rather than as prose.
   */
  shape: "tall-narrow" | "flat-wide" | "stack" | "irregular" | "no-object";
  /**
   * The model's own stated confidence in this triage call. NOT the reconstruction confidence and NOT the gate input - it is here so a wrong triage can be told apart from an unsure one.
   */
  confidence: number;
  rationale: string;
  /**
   * Exact model id that produced this, so the log says which tier answered.
   */
  model: string;
  basis: "flash-triage-v1";
  latencyMs: number;
  promptTokens?: number;
  responseTokens?: number;
}
/**
 * Why the job failed. rule is a named rule from a closed set of sentences this service owns - never a library message, never a stack trace, never a caller's bytes. Same discipline as the reconstruction service's notices.
 */
export interface JobError {
  rule: string;
  at: string;
  /**
   * Whether another delivery could plausibly succeed. A retryable failure is why the transport is allowed to redeliver; a non-retryable one is why the handler acknowledges a message it will never process rather than letting Pub/Sub redeliver it for a week.
   */
  retryable: boolean;
  actor?: JobActor;
}
/**
 * One line of the decision log: what changed the state, when, and why. The model and the confidence are repeated here as well as on the record they came from, because the trail has to read top to bottom on camera without expanding anything.
 */
export interface DecisionEntry {
  at: string;
  state: JobState;
  actor: JobActor;
  summary: string;
  model?: string;
  confidence?: number;
  latencyMs?: number;
}
