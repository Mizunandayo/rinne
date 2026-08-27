# GENERATED FILE - DO NOT EDIT BY HAND.
#
# Source of truth : packages/contracts/schemas
# Regenerate      : pwsh ./packages/contracts/scripts/generate-python.ps1
#
# CI regenerates and runs git diff --exit-code. A schema edit without a
# regeneration is a build failure.

from __future__ import annotations

from enum import IntEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class SchemaVersion(IntEnum):
    """
    Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.
    """

    integer_1 = 1


class ReconstructionRequest(BaseModel):
    """
    The JSON `request` part of a multipart/form-data POST to /v1/reconstruct. The image parts travel beside it as binary; they are deliberately NOT base64 inside this document, because that inflates the payload by a third and forces the whole body to be buffered before any of it can be validated. Everything a caller can influence lives here, and everything here is treated as untrusted: per section 12 a label or a metadata value may inform a decision but may never on its own authorize one.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: SchemaVersion = Field(..., alias="schemaVersion")
    """
    Bumped on any breaking change. A consumer that does not recognise the value must refuse the document rather than guess.
    """
    request_id: str = Field(..., alias="requestId", pattern="^[a-z0-9][a-z0-9-]{7,63}$")
    """
    Caller-supplied identifier. It becomes the GCS object name (meshes/{requestId}.glb) and later the Firestore document key, so the pattern is deliberately identical to sceneId: lowercase, no slash, no dot, no traversal. Reusing an id is a 412 from the ifGenerationMatch=0 upload rather than a silent overwrite.
    """
    captured_at: AwareDatetime | None = Field(None, alias="capturedAt")
    """
    RFC 3339 timestamp of when the photographs were taken, as reported by the client. Advisory only - the server never trusts a client clock for anything it orders by.
    """
    assumed_longest_dimension_meters: float | None = Field(
        0.3, alias="assumedLongestDimensionMeters", gt=0.0, le=5.0
    )
    """
    Single-image reconstruction recovers shape but not scale. This is the assumption the mesh is normalised to, and the result reports scaleBasis: assumed so that no downstream consumer can mistake it for a measurement. Day 7's fiducial marker replaces it with scaleBasis: measured and no contract change.
    """
    label: str | None = Field(None, max_length=120)
    """
    Short human label for the scan, shown in the cockpit. UNTRUSTED INPUT: it is model-visible text supplied by whoever called the endpoint, so it is bounded here and may never be the sole basis for a privileged action.
    """
    metadata: dict[str, str] | None = Field(None, max_length=16)
    """
    Free-form string pairs carried through to the result for correlation. Bounded by count here and by total serialised size (max_metadata_chars) in the service. Values carry no maxLength ON PURPOSE: adding one makes datamodel-codegen emit a RootModel wrapper that every use site would have to unwrap.
    """
