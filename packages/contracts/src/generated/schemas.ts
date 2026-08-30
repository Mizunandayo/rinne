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

export const agentJobSchema = {
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://rinne.dev/schemas/agent-job.schema.json",
  "title": "AgentJob",
  "description": "One scan, one Firestore document, one exhaustive state machine. This is the decision log section 7 promises, and the only place a job's state lives - there is no in-process table it could disagree with. It is a shared contract rather than a private shape because the cockpit reads it from TypeScript, and because generating the ten states into both languages is what turns \"no implicit states\" into a build gate instead of a discipline.",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schemaVersion",
    "jobId",
    "state",
    "attempts",
    "createdAt",
    "updatedAt",
    "source",
    "decisions"
  ],
  "properties": {
    "schemaVersion": {
      "description": "Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.",
      "type": "integer",
      "enum": [
        1
      ]
    },
    "jobId": {
      "description": "Firestore document key, and later the reconstruction requestId and the sceneId. Derived deterministically from bucket, object and generation so a redelivered event maps to the same document instead of a second job. Same pattern as requestId and sceneId, for the same reason: no slash, no dot, no traversal.",
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9-]{7,63}$"
    },
    "state": {
      "$ref": "#/definitions/jobState"
    },
    "lastGoodState": {
      "$ref": "#/definitions/jobState"
    },
    "attempts": {
      "description": "How many times the agent has begun work on this job. Section 12 forbids unbounded loops; this is where that rule is enforced for the agent path, and the ceiling of 6 matches the tool-loop cap and SceneDescription.provenance.refitIteration.",
      "type": "integer",
      "minimum": 0,
      "maximum": 6
    },
    "createdAt": {
      "description": "RFC 3339 timestamp of the delivery that created this document.",
      "type": "string",
      "format": "date-time"
    },
    "updatedAt": {
      "description": "RFC 3339 timestamp of the last accepted transition.",
      "type": "string",
      "format": "date-time"
    },
    "source": {
      "$ref": "#/definitions/scanSource"
    },
    "triage": {
      "$ref": "#/definitions/triageRecord"
    },
    "error": {
      "$ref": "#/definitions/jobError"
    },
    "selection": {
      "$ref": "#/definitions/selectionRecord"
    },
    "reconstruction": {
      "$ref": "#/definitions/reconstructionRecord"
    },
    "simulation": {
      "$ref": "#/definitions/simulationRecord"
    },
    "gate": {
      "$ref": "#/definitions/gateRecord"
    },
    "decisions": {
      "description": "Append-only audit trail. Bounded so a redelivery storm or a buggy loop cannot inflate a document, and because Firestore charges by document size.",
      "type": "array",
      "maxItems": 24,
      "items": {
        "$ref": "#/definitions/decisionEntry"
      }
    }
  },
  "definitions": {
    "jobState": {
      "description": "The exhaustive state set from section 7. skipped_low_risk is a LEGITIMATE terminal outcome and the most common one - triage deciding no review is needed is the product working, not failing. gated is designed and NOT shipped: the Gemma tier-0 gate was cut on Aug 28, so nothing in this build emits it; it stays in the enum so the three-tier cascade remains describable and the cut remains visible. failed is reachable from every non-terminal state and carries error and lastGoodState.",
      "type": "string",
      "enum": [
        "queued",
        "gated",
        "skipped_low_risk",
        "triaged",
        "simulating",
        "awaiting_verification",
        "refitting",
        "reporting",
        "done",
        "failed"
      ]
    },
    "scanSource": {
      "description": "The object that triggered this job, as reported by the storage event. Recorded in full so the decision log is reproducible from the document alone - a judge can re-run the exact object the agent saw.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "bucket",
        "object",
        "generation",
        "contentType",
        "sizeBytes",
        "receivedAt"
      ],
      "properties": {
        "bucket": {
          "description": "Checked against one configured bucket before any work happens. The delivery is authenticated by IAM, but the bucket name inside it is still payload.",
          "type": "string",
          "pattern": "^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$"
        },
        "object": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        },
        "generation": {
          "description": "GCS reports generation as a decimal string, and it stays a string here for the same reason: it is an int64 identifier, not a number anything does arithmetic on. It is part of the jobId derivation, so overwriting an object produces a new job rather than silently reusing the old one.",
          "type": "string",
          "pattern": "^[0-9]{1,20}$"
        },
        "contentType": {
          "description": "Allowlisted before the object is read. The same three types the reconstruction service accepts, so a scan that triages cannot then be refused downstream.",
          "type": "string",
          "enum": [
            "image/jpeg",
            "image/png",
            "image/webp"
          ]
        },
        "sizeBytes": {
          "type": "integer",
          "minimum": 1,
          "maximum": 26214400
        },
        "receivedAt": {
          "type": "string",
          "format": "date-time"
        },
        "eventId": {
          "description": "CloudEvent id of the delivery that created the job. Two deliveries of one object carry the same id; a genuine re-upload does not. Evidence, not a control - the control is the create-only write.",
          "type": "string",
          "maxLength": 128
        }
      }
    },
    "triageRecord": {
      "description": "Section 7 step 1. The judgment a script cannot make: is this object worth a physics review at all. shape is the classification the decision rested on, and it is the input Day 5's test selection reads - recording it here means selection does not have to look at the image a second time.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "review",
        "shape",
        "confidence",
        "rationale",
        "model",
        "basis",
        "latencyMs"
      ],
      "properties": {
        "review": {
          "description": "true: this warrants a physics review, and the job moves to triaged. false: it does not, and the job terminates in skipped_low_risk.",
          "type": "boolean"
        },
        "shape": {
          "description": "What the model saw. no-object is the case the cut Gemma tier-0 gate would have caught more cheaply; Flash catches it now, which is the cost argument for that gate written down as a value rather than as prose.",
          "type": "string",
          "enum": [
            "tall-narrow",
            "flat-wide",
            "stack",
            "irregular",
            "no-object"
          ]
        },
        "confidence": {
          "description": "The model's own stated confidence in this triage call. NOT the reconstruction confidence and NOT the gate input - it is here so a wrong triage can be told apart from an unsure one.",
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "rationale": {
          "type": "string",
          "minLength": 1,
          "maxLength": 280
        },
        "model": {
          "description": "Exact model id that produced this, so the log says which tier answered.",
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "basis": {
          "type": "string",
          "enum": [
            "flash-triage-v1"
          ]
        },
        "latencyMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        },
        "promptTokens": {
          "type": "integer",
          "minimum": 0,
          "maximum": 10000000
        },
        "responseTokens": {
          "type": "integer",
          "minimum": 0,
          "maximum": 10000000
        }
      }
    },
    "jobError": {
      "description": "Why the job failed. rule is a named rule from a closed set of sentences this service owns - never a library message, never a stack trace, never a caller's bytes. Same discipline as the reconstruction service's notices.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "rule",
        "at",
        "retryable"
      ],
      "properties": {
        "rule": {
          "type": "string",
          "minLength": 1,
          "maxLength": 200
        },
        "at": {
          "type": "string",
          "format": "date-time"
        },
        "retryable": {
          "description": "Whether another delivery could plausibly succeed. A retryable failure is why the transport is allowed to redeliver; a non-retryable one is why the handler acknowledges a message it will never process rather than letting Pub/Sub redeliver it for a week.",
          "type": "boolean"
        },
        "actor": {
          "$ref": "#/definitions/jobActor"
        }
      }
    },
    "decisionEntry": {
      "description": "One line of the decision log: what changed the state, when, and why. The model and the confidence are repeated here as well as on the record they came from, because the trail has to read top to bottom on camera without expanding anything.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "at",
        "state",
        "actor",
        "summary"
      ],
      "properties": {
        "at": {
          "type": "string",
          "format": "date-time"
        },
        "state": {
          "$ref": "#/definitions/jobState"
        },
        "actor": {
          "$ref": "#/definitions/jobActor"
        },
        "summary": {
          "type": "string",
          "minLength": 1,
          "maxLength": 240
        },
        "model": {
          "type": "string",
          "maxLength": 64
        },
        "confidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "latencyMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        }
      }
    },
    "jobActor": {
      "description": "Which step of the loop acted. Closed so the dashboard can group by it, and so a step that does not exist yet cannot appear in a log without a schema change.",
      "type": "string",
      "enum": [
        "ingest",
        "triage",
        "gate",
        "reconstruction",
        "physics",
        "refit",
        "report",
        "operator"
      ]
    },
    "testKind": {
      "description": "Which physics test the agent selected. Mirrors the oneOf kinds in scene-description.schema.json; none is what a shape that cannot be tested gets.",
      "type": "string",
      "enum": [
        "tip",
        "load",
        "drop",
        "none"
      ]
    },
    "selectionRecord": {
      "description": "Section 7 step 2. Different objects genuinely receive different tool calls, and this is where that shows in the log. The model chooses from a closed set; it does not invent a test.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "kind",
        "rationale",
        "confidence",
        "model",
        "basis",
        "latencyMs"
      ],
      "properties": {
        "kind": {
          "$ref": "#/definitions/testKind"
        },
        "rationale": {
          "type": "string",
          "minLength": 1,
          "maxLength": 280
        },
        "confidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "model": {
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "basis": {
          "type": "string",
          "enum": [
            "flash-selection-v1"
          ]
        },
        "latencyMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        },
        "promptTokens": {
          "type": "integer",
          "minimum": 0,
          "maximum": 10000000
        },
        "responseTokens": {
          "type": "integer",
          "minimum": 0,
          "maximum": 10000000
        }
      }
    },
    "reconstructionRecord": {
      "description": "What POST /v1/reconstruct returned, reduced to the fields the gate and the cockpit read. The full ReconstructionResult is not copied here - the mesh URI is the pointer to everything else.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "requestId",
        "meshUri",
        "confidence",
        "band",
        "calibrated",
        "material",
        "materialConfidence",
        "latencyMs"
      ],
      "properties": {
        "requestId": {
          "type": "string",
          "pattern": "^[a-z0-9][a-z0-9-]{7,63}$"
        },
        "meshUri": {
          "type": "string",
          "pattern": "^gs://[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]/.{1,512}$"
        },
        "confidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "band": {
          "type": "string",
          "enum": [
            "low",
            "medium",
            "high"
          ]
        },
        "calibrated": {
          "type": "boolean"
        },
        "material": {
          "type": "string",
          "enum": [
            "cardboard",
            "wood",
            "plastic",
            "metal",
            "glass",
            "fabric",
            "unknown"
          ]
        },
        "materialConfidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "massKilograms": {
          "type": "number",
          "exclusiveMinimum": 0,
          "maximum": 5000
        },
        "faceCount": {
          "type": "integer",
          "minimum": 0,
          "maximum": 10000000
        },
        "watertight": {
          "type": "boolean"
        },
        "pipeline": {
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "latencyMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        }
      }
    },
    "simulationRecord": {
      "description": "What POST /v1/simulate returned. inconclusive is the engine refusing to guess rather than an error, and the gate treats it as a first-class reason to ask a human.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "sceneId",
        "verdict",
        "settled",
        "steps",
        "tiltDegrees",
        "driftMeters",
        "digest",
        "latencyMs"
      ],
      "properties": {
        "sceneId": {
          "type": "string",
          "pattern": "^[a-z0-9][a-z0-9-]{7,63}$"
        },
        "verdict": {
          "type": "string",
          "enum": [
            "stable",
            "tipped",
            "slid",
            "inconclusive"
          ]
        },
        "settled": {
          "type": "boolean"
        },
        "steps": {
          "type": "integer",
          "minimum": 0,
          "maximum": 20000
        },
        "tiltDegrees": {
          "type": "number",
          "minimum": 0,
          "maximum": 180
        },
        "driftMeters": {
          "type": "number",
          "minimum": 0,
          "maximum": 100000
        },
        "digest": {
          "type": "string",
          "pattern": "^[a-f0-9]{16}$"
        },
        "hullVertices": {
          "type": "integer",
          "minimum": 0,
          "maximum": 100000
        },
        "latencyMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        },
        "notices": {
          "description": "Notice codes the physics service attached. load-test-not-implemented is the one the gate acts on: an unsupported test settles untouched and reports a meaningless stable.",
          "type": "array",
          "maxItems": 8,
          "items": {
            "$ref": "#/definitions/noticeCode"
          }
        }
      }
    },
    "noticeCode": {
      "description": "One advisory the physics service attached to a result. These are not failures; they are the caveats a viewer has to see before believing a verdict.",
      "type": "string",
      "enum": [
        "collider-is-convex-hull",
        "collider-decimated",
        "center-of-mass-not-applied",
        "did-not-settle",
        "left-the-ground-plane",
        "load-test-not-implemented"
      ]
    },
    "gateInput": {
      "description": "One measured value the policy compared against one threshold. physics-verdict is 0.0 when the engine answered inconclusive and 1.0 otherwise, so every input renders the same way.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "name",
        "value",
        "threshold",
        "passed"
      ],
      "properties": {
        "name": {
          "type": "string",
          "enum": [
            "reconstruction-confidence",
            "material-confidence",
            "physics-verdict"
          ]
        },
        "value": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "threshold": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "passed": {
          "type": "boolean"
        }
      }
    },
    "gateReason": {
      "description": "Why the gate refused. A closed set so the cockpit can branch on it. physics-test-unsupported is the load test: the engine accepts the scene, applies no force, and settles to a stable that means nothing - so the agent asks a human rather than reporting it.",
      "type": "string",
      "enum": [
        "low-reconstruction-confidence",
        "low-material-confidence",
        "physics-inconclusive",
        "physics-test-unsupported"
      ]
    },
    "gateRecord": {
      "description": "THE DECLARED POLICY, section 7 step 3. Never a bare if: the record names the rule, the threshold it used, every input it compared, and whether those thresholds were ever measured. That is what makes a refusal auditable and the threshold configurable without a code change.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "policy",
        "threshold",
        "observed",
        "calibrated",
        "decision",
        "inputs",
        "at"
      ],
      "properties": {
        "policy": {
          "description": "The rule's name and version. A threshold change keeps the name; a change to WHAT is compared bumps it.",
          "type": "string",
          "enum": [
            "min-confidence-v1"
          ]
        },
        "threshold": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "observed": {
          "description": "The binding input - the lowest value the policy saw. This is the number that decided it.",
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "calibrated": {
          "description": "Whether the thresholds were measured against real objects or are still documented guesses. Reported either way; it does not change the decision.",
          "type": "boolean"
        },
        "decision": {
          "type": "string",
          "enum": [
            "report",
            "escalate"
          ]
        },
        "inputs": {
          "type": "array",
          "maxItems": 6,
          "items": {
            "$ref": "#/definitions/gateInput"
          }
        },
        "reasons": {
          "type": "array",
          "maxItems": 6,
          "items": {
            "$ref": "#/definitions/gateReason"
          }
        },
        "at": {
          "type": "string",
          "format": "date-time"
        }
      }
    }
  }
} as const;

export const healthSchema = {
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://rinne.dev/schemas/health.schema.json",
  "title": "HealthReport",
  "description": "Uniform liveness and readiness payload returned by every Rinne service. The web service's manifest page renders this, and smoke-test.ps1 asserts against it, so the shape is a contract and not a convenience.",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "service",
    "status",
    "version",
    "checkedAt"
  ],
  "properties": {
    "service": {
      "description": "Which Rinne service produced this report.",
      "type": "string",
      "enum": [
        "web",
        "physics",
        "agent",
        "reconstruction"
      ]
    },
    "status": {
      "description": "ok: fully serving. degraded: serving with a failed non-critical dependency. down: not serving.",
      "type": "string",
      "enum": [
        "ok",
        "degraded",
        "down"
      ]
    },
    "version": {
      "description": "Build identifier. Set from the image tag at deploy time.",
      "type": "string",
      "minLength": 1,
      "maxLength": 64
    },
    "checkedAt": {
      "description": "RFC 3339 timestamp of this check, produced at request time and never cached.",
      "type": "string",
      "format": "date-time"
    },
    "revision": {
      "description": "Cloud Run revision name, from the K_REVISION environment variable.",
      "type": "string",
      "maxLength": 128
    },
    "region": {
      "description": "Deployment region, for confirming the asia-southeast1 decision holds in production.",
      "type": "string",
      "maxLength": 32
    },
    "detail": {
      "description": "Short operator-facing note. Never contains a stack trace, an internal hostname, or a credential.",
      "type": "string",
      "maxLength": 256
    },
    "dependencies": {
      "description": "Downstream checks this service performed. Bounded so a compromised or buggy downstream cannot inflate a response.",
      "type": "array",
      "maxItems": 16,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "name",
          "status"
        ],
        "properties": {
          "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64
          },
          "status": {
            "type": "string",
            "enum": [
              "ok",
              "degraded",
              "down"
            ]
          },
          "latencyMs": {
            "type": "integer",
            "minimum": 0,
            "maximum": 600000
          },
          "detail": {
            "type": "string",
            "maxLength": 256
          }
        }
      }
    }
  }
} as const;

export const reconstructionRequestSchema = {
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://rinne.dev/schemas/reconstruction-request.schema.json",
  "title": "ReconstructionRequest",
  "description": "The JSON `request` part of a multipart/form-data POST to /v1/reconstruct. The image parts travel beside it as binary; they are deliberately NOT base64 inside this document, because that inflates the payload by a third and forces the whole body to be buffered before any of it can be validated. Everything a caller can influence lives here, and everything here is treated as untrusted: per section 12 a label or a metadata value may inform a decision but may never on its own authorize one.",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schemaVersion",
    "requestId"
  ],
  "properties": {
    "schemaVersion": {
      "description": "Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.",
      "type": "integer",
      "enum": [
        1
      ]
    },
    "requestId": {
      "description": "Caller-supplied identifier. It becomes the GCS object name (meshes/{requestId}.glb) and later the Firestore document key, so the pattern is deliberately identical to sceneId: lowercase, no slash, no dot, no traversal. Reusing an id is a 412 from the ifGenerationMatch=0 upload rather than a silent overwrite.",
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9-]{7,63}$"
    },
    "capturedAt": {
      "description": "RFC 3339 timestamp of when the photographs were taken, as reported by the client. Advisory only - the server never trusts a client clock for anything it orders by.",
      "type": "string",
      "format": "date-time"
    },
    "assumedLongestDimensionMeters": {
      "description": "Single-image reconstruction recovers shape but not scale. This is the assumption the mesh is normalised to, and the result reports scaleBasis: assumed so that no downstream consumer can mistake it for a measurement. Day 7's fiducial marker replaces it with scaleBasis: measured and no contract change.",
      "type": "number",
      "exclusiveMinimum": 0,
      "maximum": 5,
      "default": 0.3
    },
    "label": {
      "description": "Short human label for the scan, shown in the cockpit. UNTRUSTED INPUT: it is model-visible text supplied by whoever called the endpoint, so it is bounded here and may never be the sole basis for a privileged action.",
      "type": "string",
      "maxLength": 120
    },
    "metadata": {
      "description": "Free-form string pairs carried through to the result for correlation. Bounded by count here and by total serialised size (max_metadata_chars) in the service. Values carry no maxLength ON PURPOSE: adding one makes datamodel-codegen emit a RootModel wrapper that every use site would have to unwrap.",
      "type": "object",
      "maxProperties": 16,
      "additionalProperties": {
        "type": "string"
      }
    }
  }
} as const;

export const reconstructionResultSchema = {
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://rinne.dev/schemas/reconstruction-result.schema.json",
  "title": "ReconstructionResult",
  "description": "What POST /v1/reconstruct returns on success. There is no status field: either this document comes back with 200, or the caller gets a 4xx/5xx error envelope. Nothing in between. Every number here is measured by the service rather than asserted, and the confidence weights ship inside the payload so the score is recomputable by anyone holding the response.",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schemaVersion",
    "requestId",
    "completedAt",
    "mesh",
    "material",
    "confidence",
    "pipeline",
    "images",
    "timings"
  ],
  "properties": {
    "schemaVersion": {
      "description": "Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.",
      "type": "integer",
      "enum": [
        1
      ]
    },
    "requestId": {
      "description": "Echoed from the request, and the key the mesh object was written under.",
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9-]{7,63}$"
    },
    "completedAt": {
      "description": "RFC 3339 timestamp taken on the server after the upload succeeded.",
      "type": "string",
      "format": "date-time"
    },
    "mesh": {
      "$ref": "#/definitions/reconstructedMesh"
    },
    "material": {
      "$ref": "#/definitions/materialEstimate"
    },
    "confidence": {
      "$ref": "#/definitions/reconstructionConfidence"
    },
    "pipeline": {
      "$ref": "#/definitions/pipelineInfo"
    },
    "images": {
      "$ref": "#/definitions/imageAccounting"
    },
    "timings": {
      "$ref": "#/definitions/stageTimings"
    },
    "notices": {
      "description": "Bounded list of things the caller should know about this result - an assumed scale, an uncalibrated confidence, a stub pipeline. Named rules, never library messages.",
      "type": "array",
      "maxItems": 8,
      "items": {
        "$ref": "#/definitions/reconstructionNotice"
      }
    }
  },
  "definitions": {
    "reconstructedMesh": {
      "description": "The stored artifact plus the measurements taken from it. The physics service and the agent both read these, so they live in the contract rather than being recomputed twice and disagreeing.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "uri",
        "format",
        "byteLength",
        "vertexCount",
        "faceCount",
        "watertight",
        "extent",
        "volumeCubicMeters",
        "upAxis",
        "scaleBasis"
      ],
      "properties": {
        "uri": {
          "description": "gs:// ONLY, matching the meshRef precedent in scene-description.schema.json. The physics service fetches this URI and this document is shaped by model output, so an unrestricted scheme here is a server-side request forgery primitive pointed at the metadata server. Restricting the scheme at the contract boundary kills that class of attack once, rather than in every handler that might forget.",
          "type": "string",
          "pattern": "^gs://[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]/.{1,512}$"
        },
        "format": {
          "type": "string",
          "enum": [
            "glb"
          ]
        },
        "sha256": {
          "description": "Integrity check on the stored asset, computed over the exact bytes uploaded.",
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        },
        "byteLength": {
          "description": "Size of the stored GLB, so a viewer can budget its fetch before starting it.",
          "type": "integer",
          "minimum": 1,
          "maximum": 104857600
        },
        "vertexCount": {
          "type": "integer",
          "minimum": 0,
          "maximum": 10000000
        },
        "faceCount": {
          "type": "integer",
          "minimum": 0,
          "maximum": 10000000
        },
        "watertight": {
          "description": "Reported by trimesh AFTER normalisation. Marching cubes routinely produces duplicate vertices and degenerate faces, either of which makes a genuinely closed surface report false, so this is measured post-merge or it is meaningless.",
          "type": "boolean"
        },
        "extent": {
          "$ref": "#/definitions/meshExtent"
        },
        "volumeCubicMeters": {
          "description": "Signed volume magnitude of the normalised mesh. Feeds volumePlausibility and the mass estimate.",
          "type": "number",
          "minimum": 0,
          "maximum": 1000
        },
        "upAxis": {
          "description": "Y, always. Marching cubes emits Z-up; normalisation rotates it once here so no consumer has to guess.",
          "type": "string",
          "enum": [
            "y"
          ]
        },
        "scaleBasis": {
          "description": "assumed: scale came from assumedLongestDimensionMeters and is a guess. measured: scale came from a fiducial marker of known size. Day 7 flips this value with no contract change, which is the entire reason it is an enum and not a boolean.",
          "type": "string",
          "enum": [
            "assumed",
            "measured"
          ]
        }
      }
    },
    "meshExtent": {
      "description": "Axis-aligned bounding box dimensions in metres, after normalisation. Not named vec3: every definitions key becomes a flat top-level TypeScript identifier and scene-description.schema.json already owns that name.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "x",
        "y",
        "z"
      ],
      "properties": {
        "x": {
          "type": "number",
          "minimum": 0,
          "maximum": 100
        },
        "y": {
          "type": "number",
          "minimum": 0,
          "maximum": 100
        },
        "z": {
          "type": "number",
          "minimum": 0,
          "maximum": 100
        }
      }
    },
    "materialEstimate": {
      "description": "The physical properties the physics service needs, plus how confident the service is that they are right. The confidences are low on purpose: a weak material signal SHOULD push a borderline job into escalation rather than quietly through it.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "name",
        "basis",
        "confidence",
        "densityKilogramsPerCubicMeter",
        "massKilograms",
        "friction",
        "restitution"
      ],
      "properties": {
        "name": {
          "type": "string",
          "enum": [
            "cardboard",
            "wood",
            "plastic",
            "metal",
            "glass",
            "fabric",
            "unknown"
          ]
        },
        "basis": {
          "description": "How the guess was made. heuristic-v1 is the mean-vertex-colour HSV classifier. flash-vision-v1 is the Gemini Flash call that replaces it on Day 4 - it is in the enum now so that swap is a config change rather than a contract change.",
          "type": "string",
          "enum": [
            "heuristic-v1",
            "flash-vision-v1"
          ]
        },
        "confidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "densityKilogramsPerCubicMeter": {
          "type": "number",
          "exclusiveMinimum": 0,
          "maximum": 25000
        },
        "massKilograms": {
          "description": "density * max(volume * solidFraction, 1e-6), capped at 5000 and floored at 1e-4. The bounds match rigidBody.massKilograms so a result drops straight into a SceneDescription.",
          "type": "number",
          "exclusiveMinimum": 0,
          "maximum": 5000
        },
        "friction": {
          "type": "number",
          "minimum": 0,
          "maximum": 2
        },
        "restitution": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        }
      }
    },
    "reconstructionConfidence": {
      "description": "The number the confidence gate reads in section 7 step 3. It ships with its own components AND its own weights so that a judge, a test, or the agent can recompute it from the response alone.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "score",
        "band",
        "calibrated",
        "components",
        "weights"
      ],
      "properties": {
        "score": {
          "description": "Weighted sum of the components below. Hard floor: a mesh under 100 faces scores 0.0 regardless of components, because there is nothing there to be confident about.",
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "band": {
          "description": "Coarse bucket for the UI and for the escalation decision. The thresholds are documented guesses in config until Day 3 measures them against three real objects, which is what calibrated reports.",
          "type": "string",
          "enum": [
            "low",
            "medium",
            "high"
          ]
        },
        "calibrated": {
          "description": "false until the band thresholds have been measured rather than guessed. Saying so in the payload is cheaper than being asked on camera.",
          "type": "boolean"
        },
        "components": {
          "$ref": "#/definitions/confidenceComponents"
        },
        "weights": {
          "$ref": "#/definitions/confidenceWeights"
        }
      }
    },
    "confidenceComponents": {
      "description": "Each component is measured, in [0,1], and rounded to 4dp so tests are deterministic. foregroundQuality is OPTIONAL because it derives from the segmentation mask, which ships with TripoSR; a build without segmentation omits the key entirely rather than inventing a value for it.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "fieldDecisiveness",
        "watertightness",
        "volumePlausibility"
      ],
      "properties": {
        "fieldDecisiveness": {
          "description": "How far the density field sat from the iso-surface, sampled one voxel in 64 by the marching-cubes shim. A field that hovers near the threshold everywhere produced a surface that could have gone either way.",
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "watertightness": {
          "description": "1.0 for a closed surface, otherwise scaled by the share of boundary edges - rows of edges_sorted appearing exactly once.",
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "volumePlausibility": {
          "description": "Occupancy of the bounding box, through a triangular window peaking at 0.5 and reaching zero at 0.03 and 1.0. Catches both the wisp and the solid block.",
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "foregroundQuality": {
          "description": "framing * cropping, from the segmentation mask. Absent until segmentation ships, at which point the weights below regain their fourth entry.",
          "type": "number",
          "minimum": 0,
          "maximum": 1
        }
      }
    },
    "confidenceWeights": {
      "description": "The exact weights used for THIS response. They sum to 1.0, and they change when a component is added or removed - which is precisely why they are transmitted rather than documented. Same optionality as the components: no foregroundQuality weight without a foregroundQuality component.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "fieldDecisiveness",
        "watertightness",
        "volumePlausibility"
      ],
      "properties": {
        "fieldDecisiveness": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "watertightness": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "volumePlausibility": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "foregroundQuality": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        }
      }
    },
    "pipelineInfo": {
      "description": "Which reconstructor actually ran. This exists so a placeholder can say it is a placeholder, in the payload, without anybody having to remember to mention it.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "name",
        "version",
        "device"
      ],
      "properties": {
        "name": {
          "description": "stub: a deterministic procedural mesh, honest about being one. triposr: the real model.",
          "type": "string",
          "enum": [
            "stub",
            "triposr"
          ]
        },
        "version": {
          "description": "Pipeline build identifier. For triposr this is the pinned upstream commit SHA, which is what makes vendoring at a known state a truthful claim rather than a hope.",
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "device": {
          "type": "string",
          "enum": [
            "cpu",
            "cuda"
          ]
        },
        "seed": {
          "description": "Determinism seed, when the pipeline takes one. Same role as SceneDescription.solver.seed.",
          "type": "integer",
          "minimum": 0,
          "maximum": 4294967295
        }
      }
    },
    "imageAccounting": {
      "description": "What happened to the uploaded images. reencoded is the visible proof of validation layer 7: the model never saw a byte the client sent, which is what strips EXIF GPS and kills polyglot payloads.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "received",
        "accepted",
        "used",
        "reencoded",
        "longestEdgePixels"
      ],
      "properties": {
        "received": {
          "type": "integer",
          "minimum": 1,
          "maximum": 4
        },
        "accepted": {
          "type": "integer",
          "minimum": 0,
          "maximum": 4
        },
        "used": {
          "description": "How many accepted images the pipeline actually consumed. Day 2 accepts up to four and uses the first; that narrowing is behaviour inside an unchanged contract, and this field is where it is admitted.",
          "type": "integer",
          "minimum": 0,
          "maximum": 4
        },
        "reencoded": {
          "type": "boolean"
        },
        "longestEdgePixels": {
          "description": "Longest edge of the re-encoded image handed to the pipeline, after the bound in max_image_edge.",
          "type": "integer",
          "minimum": 1,
          "maximum": 8192
        }
      }
    },
    "stageTimings": {
      "description": "Wall-clock milliseconds per stage. Read on camera, and the cheapest way to see a cold GPU start for what it is.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "validationMs",
        "inferenceMs",
        "meshMs",
        "uploadMs",
        "totalMs"
      ],
      "properties": {
        "validationMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        },
        "inferenceMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        },
        "meshMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        },
        "uploadMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        },
        "totalMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        }
      }
    },
    "reconstructionNotice": {
      "description": "One caveat about this result. The code is a closed enum so a consumer can branch on it; the message is for a human and is a fixed sentence, never a library string, a filename, or a byte range.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "code",
        "severity",
        "message"
      ],
      "properties": {
        "code": {
          "type": "string",
          "enum": [
            "stub-pipeline",
            "scale-assumed",
            "confidence-uncalibrated",
            "foreground-quality-unavailable",
            "images-ignored",
            "material-weak-signal",
            "low-face-count",
            "mesh-not-watertight"
          ]
        },
        "severity": {
          "type": "string",
          "enum": [
            "info",
            "warning"
          ]
        },
        "message": {
          "type": "string",
          "minLength": 1,
          "maxLength": 200
        }
      }
    }
  }
} as const;

export const sceneDescriptionSchema = {
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://rinne.dev/schemas/scene-description.schema.json",
  "title": "SceneDescription",
  "description": "Portable, engine-agnostic physics scene. This is the single interchange format between the browser Rapier build, the headless Node Rapier build, and the Python agent, and it is also the exportable simulation artifact. Two hosts given the same document must produce the same result; anything that would let them diverge does not belong in this file.",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schemaVersion",
    "sceneId",
    "units",
    "gravity",
    "ground",
    "body",
    "test",
    "solver"
  ],
  "properties": {
    "schemaVersion": {
      "description": "Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.",
      "type": "integer",
      "enum": [
        1
      ]
    },
    "sceneId": {
      "description": "Stable identifier, also used as the Firestore document key.",
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9-]{7,63}$"
    },
    "units": {
      "description": "Declared explicitly so a unit mismatch is a validation error rather than a physics result that is wrong by a factor of a thousand.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "length",
        "mass"
      ],
      "properties": {
        "length": {
          "type": "string",
          "enum": [
            "m"
          ]
        },
        "mass": {
          "type": "string",
          "enum": [
            "kg"
          ]
        }
      }
    },
    "gravity": {
      "$ref": "#/definitions/vec3"
    },
    "ground": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "friction",
        "restitution"
      ],
      "properties": {
        "friction": {
          "type": "number",
          "minimum": 0,
          "maximum": 2
        },
        "restitution": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        }
      }
    },
    "body": {
      "$ref": "#/definitions/rigidBody"
    },
    "test": {
      "description": "Which physics test the agent selected. Exactly one, chosen per §7 step 2.",
      "oneOf": [
        {
          "title": "TipTest",
          "type": "object",
          "additionalProperties": false,
          "required": [
            "kind",
            "pushHeightRatio",
            "forceNewtons",
            "directionDegrees"
          ],
          "properties": {
            "kind": {
              "type": "string",
              "enum": [
                "tip"
              ]
            },
            "pushHeightRatio": {
              "description": "Height of the applied push as a fraction of the object's total height.",
              "type": "number",
              "minimum": 0,
              "maximum": 1
            },
            "forceNewtons": {
              "type": "number",
              "minimum": 0,
              "maximum": 5000
            },
            "directionDegrees": {
              "type": "number",
              "minimum": 0,
              "exclusiveMaximum": 360
            },
            "durationSeconds": {
              "type": "number",
              "minimum": 0,
              "maximum": 5
            }
          }
        },
        {
          "title": "LoadTest",
          "type": "object",
          "additionalProperties": false,
          "required": [
            "kind",
            "loadKilograms",
            "contactRadius"
          ],
          "properties": {
            "kind": {
              "type": "string",
              "enum": [
                "load"
              ]
            },
            "loadKilograms": {
              "type": "number",
              "minimum": 0,
              "maximum": 2000
            },
            "contactRadius": {
              "type": "number",
              "minimum": 0,
              "maximum": 5
            },
            "offsetFromCenter": {
              "$ref": "#/definitions/vec3"
            }
          }
        },
        {
          "title": "DropTest",
          "type": "object",
          "additionalProperties": false,
          "required": [
            "kind",
            "dropHeightMeters"
          ],
          "properties": {
            "kind": {
              "type": "string",
              "enum": [
                "drop"
              ]
            },
            "dropHeightMeters": {
              "type": "number",
              "minimum": 0,
              "maximum": 20
            },
            "initialRotationDegrees": {
              "$ref": "#/definitions/vec3"
            }
          }
        }
      ]
    },
    "solver": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "timestepSeconds",
        "maxSteps",
        "seed"
      ],
      "properties": {
        "timestepSeconds": {
          "type": "number",
          "minimum": 0.0005,
          "maximum": 0.05
        },
        "maxSteps": {
          "description": "Hard upper bound on simulation steps. §12 forbids unbounded loops, and this is where that rule is enforced for the physics path — the schema makes an unbounded simulation unrepresentable.",
          "type": "integer",
          "minimum": 1,
          "maximum": 20000
        },
        "substeps": {
          "type": "integer",
          "minimum": 1,
          "maximum": 16
        },
        "seed": {
          "description": "Determinism seed. Both hosts must use it, or the shared-engine claim is unverifiable.",
          "type": "integer",
          "minimum": 0,
          "maximum": 4294967295
        }
      }
    },
    "provenance": {
      "description": "Where the estimates in this document came from. Read by the confidence gate in §7 step 3.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "source"
      ],
      "properties": {
        "source": {
          "type": "string",
          "enum": [
            "agent",
            "cockpit",
            "refit",
            "fixture"
          ]
        },
        "estimatedBy": {
          "type": "string",
          "maxLength": 64
        },
        "reconstructionConfidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "materialConfidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "refitIteration": {
          "type": "integer",
          "minimum": 0,
          "maximum": 6
        }
      }
    }
  },
  "definitions": {
    "vec3": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "x",
        "y",
        "z"
      ],
      "properties": {
        "x": {
          "type": "number",
          "minimum": -1000,
          "maximum": 1000
        },
        "y": {
          "type": "number",
          "minimum": -1000,
          "maximum": 1000
        },
        "z": {
          "type": "number",
          "minimum": -1000,
          "maximum": 1000
        }
      }
    },
    "meshRef": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "uri",
        "format"
      ],
      "properties": {
        "uri": {
          "description": "gs:// ONLY. The physics service fetches this URI, and this document is shaped by model output, so an unrestricted scheme here is a server-side request forgery primitive pointed at the metadata server. Restricting the scheme in the schema kills that class of attack at the contract boundary rather than in a handler someone might forget to write.",
          "type": "string",
          "pattern": "^gs://[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]/.{1,512}$"
        },
        "format": {
          "type": "string",
          "enum": [
            "glb"
          ]
        },
        "sha256": {
          "description": "Integrity check on the fetched asset. Optional on Day 3, required once the cockpit and the agent fetch the same mesh.",
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        }
      }
    },
    "rigidBody": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "mesh",
        "massKilograms",
        "friction",
        "restitution",
        "initialTranslation"
      ],
      "properties": {
        "mesh": {
          "$ref": "#/definitions/meshRef"
        },
        "massKilograms": {
          "type": "number",
          "exclusiveMinimum": 0,
          "maximum": 5000
        },
        "centerOfMass": {
          "$ref": "#/definitions/vec3"
        },
        "friction": {
          "type": "number",
          "minimum": 0,
          "maximum": 2
        },
        "restitution": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "linearDamping": {
          "type": "number",
          "minimum": 0,
          "maximum": 10
        },
        "angularDamping": {
          "type": "number",
          "minimum": 0,
          "maximum": 10
        },
        "initialTranslation": {
          "$ref": "#/definitions/vec3"
        },
        "initialRotationDegrees": {
          "$ref": "#/definitions/vec3"
        }
      }
    }
  }
} as const;

export const simulationResultSchema = {
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://rinne.dev/schemas/simulation-result.schema.json",
  "title": "SimulationResult",
  "description": "What one SceneDescription produced when it was simulated. The same scene document handed to the browser build and to the headless Node build must produce the same determinism.digest; that equality is the shared-engine claim, and parity.test.ts asserts it. Nothing host-specific belongs in this file except the host block itself, which exists precisely so a reader can tell which side produced the document.",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schemaVersion",
    "sceneId",
    "completedAt",
    "host",
    "outcome",
    "finalPose",
    "collider",
    "determinism",
    "timings"
  ],
  "properties": {
    "schemaVersion": {
      "description": "Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.",
      "type": "integer",
      "enum": [
        1
      ]
    },
    "sceneId": {
      "description": "Echoed from the SceneDescription that produced this result.",
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9-]{7,63}$"
    },
    "completedAt": {
      "description": "RFC 3339 timestamp taken after the last step. Deliberately NOT part of the determinism digest - a wall clock is the one thing two hosts can never agree on.",
      "type": "string",
      "format": "date-time"
    },
    "host": {
      "$ref": "#/definitions/simulationHost"
    },
    "outcome": {
      "$ref": "#/definitions/simulationOutcome"
    },
    "finalPose": {
      "$ref": "#/definitions/bodyPose"
    },
    "collider": {
      "$ref": "#/definitions/colliderSummary"
    },
    "determinism": {
      "$ref": "#/definitions/determinismRecord"
    },
    "timings": {
      "$ref": "#/definitions/simulationTimings"
    },
    "notices": {
      "description": "Bounded list of things the caller should know about this result - an unsettled body, a centre of mass that could not be applied, a decimated collider. Named rules, never library messages.",
      "type": "array",
      "maxItems": 8,
      "items": {
        "$ref": "#/definitions/simulationNotice"
      }
    }
  },
  "definitions": {
    "simulationHost": {
      "description": "Which side ran it. This is the only field that is allowed to differ between two runs of the same scene, and it exists so that a parity comparison can say which two things it compared.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "runtime",
        "engine",
        "engineVersion"
      ],
      "properties": {
        "runtime": {
          "type": "string",
          "enum": [
            "node",
            "browser"
          ]
        },
        "engine": {
          "type": "string",
          "enum": [
            "rapier3d-compat"
          ]
        },
        "engineVersion": {
          "type": "string",
          "minLength": 1,
          "maxLength": 32
        }
      }
    },
    "simulationOutcome": {
      "description": "The answer, plus the two measurements it was derived from. verdict is a closed enum so the agent can branch on it; tiltDegrees and driftMeters are reported so a human can see why it said that.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "verdict",
        "settled",
        "steps",
        "simulatedSeconds",
        "tiltDegrees",
        "driftMeters"
      ],
      "properties": {
        "verdict": {
          "description": "stable: settled within tolerance of where it started. tipped: settled with its up-axis more than 45 degrees from vertical. slid: settled upright but displaced more than a quarter of its longest edge. inconclusive: never settled inside solver.maxSteps, which is a real answer about the scene and not an error.",
          "type": "string",
          "enum": [
            "stable",
            "tipped",
            "slid",
            "inconclusive"
          ]
        },
        "settled": {
          "description": "True when the pose stopped changing for a full settle window. Deliberately not a velocity test: a convex hull resting on a plane keeps a small non-zero angular velocity indefinitely without moving.",
          "type": "boolean"
        },
        "steps": {
          "type": "integer",
          "minimum": 0,
          "maximum": 20000
        },
        "simulatedSeconds": {
          "type": "number",
          "minimum": 0,
          "maximum": 1000
        },
        "tiltDegrees": {
          "description": "Angle between the body's local +Y after simulation and world +Y. Yaw does not count as tilt, which is why this is measured from the up-axis rather than from the quaternion's angle.",
          "type": "number",
          "minimum": 0,
          "maximum": 180
        },
        "driftMeters": {
          "description": "Horizontal distance from the initial translation. Vertical motion is excluded: a body settling onto the ground moves down, and that is not drift.",
          "type": "number",
          "minimum": 0,
          "maximum": 100000
        }
      }
    },
    "bodyPose": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "translation",
        "rotation"
      ],
      "properties": {
        "translation": {
          "$ref": "#/definitions/poseVector"
        },
        "rotation": {
          "$ref": "#/definitions/poseRotation"
        }
      }
    },
    "poseVector": {
      "description": "Metres. Not named vec3: every definitions key becomes a flat top-level TypeScript identifier and scene-description.schema.json already owns that name.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "x",
        "y",
        "z"
      ],
      "properties": {
        "x": {
          "type": "number",
          "minimum": -100000,
          "maximum": 100000
        },
        "y": {
          "type": "number",
          "minimum": -100000,
          "maximum": 100000
        },
        "z": {
          "type": "number",
          "minimum": -100000,
          "maximum": 100000
        }
      }
    },
    "poseRotation": {
      "description": "Unit quaternion, Rapier's own component order.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "x",
        "y",
        "z",
        "w"
      ],
      "properties": {
        "x": {
          "type": "number",
          "minimum": -1,
          "maximum": 1
        },
        "y": {
          "type": "number",
          "minimum": -1,
          "maximum": 1
        },
        "z": {
          "type": "number",
          "minimum": -1,
          "maximum": 1
        },
        "w": {
          "type": "number",
          "minimum": -1,
          "maximum": 1
        }
      }
    },
    "colliderSummary": {
      "description": "What the mesh actually became. A reconstruction is not convex and this says so in the payload rather than in a comment.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "kind",
        "sourceVertices",
        "hullVertices",
        "massKilograms"
      ],
      "properties": {
        "kind": {
          "type": "string",
          "enum": [
            "convex-hull"
          ]
        },
        "sourceVertices": {
          "type": "integer",
          "minimum": 0,
          "maximum": 10000000
        },
        "hullVertices": {
          "description": "After voxel decimation. A hull built from every reconstruction vertex has hundreds of near-coplanar faces, its contact manifold flickers every step, and the body then never comes to rest - so decimation is a correctness requirement, not an optimisation.",
          "type": "integer",
          "minimum": 0,
          "maximum": 100000
        },
        "massKilograms": {
          "type": "number",
          "exclusiveMinimum": 0,
          "maximum": 5000
        }
      }
    },
    "determinismRecord": {
      "description": "Everything needed to reproduce this run, plus the digest that makes two runs comparable in one string. The digest covers the scene id, the solver settings, the verdict, the step count and the final pose at 6dp. It excludes completedAt and the host block by design.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "seed",
        "timestepSeconds",
        "substeps",
        "digest"
      ],
      "properties": {
        "seed": {
          "type": "integer",
          "minimum": 0,
          "maximum": 4294967295
        },
        "timestepSeconds": {
          "type": "number",
          "minimum": 0.0005,
          "maximum": 0.05
        },
        "substeps": {
          "type": "integer",
          "minimum": 1,
          "maximum": 16
        },
        "digest": {
          "description": "FNV-1a 64 over the canonical form, as 16 lowercase hex characters. Not a cryptographic hash and not a security control: it is a comparison key that has to compute identically and synchronously in Node and in a browser, which rules out both node:crypto and the async crypto.subtle.",
          "type": "string",
          "pattern": "^[a-f0-9]{16}$"
        }
      }
    },
    "simulationTimings": {
      "description": "Wall-clock milliseconds. Not named stageTimings: reconstruction-result.schema.json already owns that name.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "setupMs",
        "stepMs",
        "totalMs"
      ],
      "properties": {
        "setupMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        },
        "stepMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        },
        "totalMs": {
          "type": "integer",
          "minimum": 0,
          "maximum": 600000
        }
      }
    },
    "simulationNotice": {
      "description": "One caveat about this result. The code is a closed enum so a consumer can branch on it; the message is a fixed sentence for a human.",
      "type": "object",
      "additionalProperties": false,
      "required": [
        "code",
        "severity",
        "message"
      ],
      "properties": {
        "code": {
          "type": "string",
          "enum": [
            "collider-is-convex-hull",
            "collider-decimated",
            "center-of-mass-not-applied",
            "did-not-settle",
            "left-the-ground-plane",
            "load-test-not-implemented"
          ]
        },
        "severity": {
          "type": "string",
          "enum": [
            "info",
            "warning"
          ]
        },
        "message": {
          "type": "string",
          "minLength": 1,
          "maxLength": 200
        }
      }
    }
  }
} as const;
