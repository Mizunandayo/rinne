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
