"""POST /v1/reconstruct - the whole pipeline, one request.

REQUEST SHAPE is multipart/form-data: one `request` part carrying JSON that is
validated against ReconstructionRequest, plus one to four `images` parts
carrying binary. Not base64-in-JSON: that inflates the payload by a third AND
forces the entire body to be buffered before any of it can be validated.

CONCURRENCY. The service deploys at --concurrency=1, and the asyncio.Lock below
is NOT redundant with that. The flag is a deploy-time control that somebody can
raise; the lock is the code-level invariant that survives them doing it. The
blocking compute runs through anyio.to_thread so /livez keeps answering during
a twenty-second forward pass, which is the difference between a slow request
and a restart loop.

ERRORS NAME THE RULE. Never the bytes, never the filename, never a library
message. The envelope matches the agent and physics services exactly:
{"error": "...", "requestId": "..."}.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import anyio.to_thread
from fastapi import APIRouter, Request
from PIL import Image
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.requests import Request as StarletteRequest
from starlette.types import Message, Receive

from rinne_reconstruction.config import Settings
from rinne_reconstruction.contracts import ReconstructionRequest, ReconstructionResult
from rinne_reconstruction.imaging.validation import ImageValidationError, prepare_image
from rinne_reconstruction.mesh import (
    MeshNormalisationError,
    confidence,
    export_glb,
    material,
    mean_vertex_color,
    measure,
    normalise,
)
from rinne_reconstruction.pipeline.base import Reconstructor
from rinne_reconstruction.routes.health import SettingsDep
from rinne_reconstruction.storage import MeshStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["reconstruct"])

_REQUEST_PART: Final = "request"
_IMAGES_PART: Final = "images"

#: The contract bounds notices at 8, which is also exactly how many codes exist.
_MAX_NOTICES: Final = 8

_NOTICE_TEXT: Final[dict[str, str]] = {
    "stub-pipeline": "Geometry came from the stub pipeline and is a placeholder shape.",
    "scale-assumed": "Scale was assumed, not measured. No fiducial marker was present.",
    "confidence-uncalibrated": "Confidence bands are documented guesses, not measured thresholds.",
    "foreground-quality-unavailable": "This pipeline does not segment, so foregroundQuality is "
    "absent and the weights are renormalised over three components.",
    "images-ignored": "More than one image was accepted; this build reconstructs from the first.",
    "material-weak-signal": "The material heuristic matched weakly. Treat mass as provisional.",
    "low-face-count": "The surface has too few faces to be meaningful, so confidence is floored.",
    "mesh-not-watertight": "The surface is not closed. Volume and mass are approximations.",
}


class RequestRejectedError(ValueError):
    """A request failed a named rule. ``rule`` is safe to return."""

    def __init__(self, rule: str, *, status: int = 400) -> None:
        super().__init__(rule)
        self.rule = rule
        self.status = status


@dataclass(frozen=True)
class _Computed:
    """Everything the blocking phase produced, measured rather than asserted."""

    glb: bytes
    measurements: Any
    breakdown: confidence.ConfidenceBreakdown
    material_estimate: material.MaterialEstimate
    seed: int
    inference_ms: int
    mesh_ms: int


def _replay_receive(body: bytes) -> Receive:
    """Hand an already-read body back to Starlette's own form parser.

    The body must be COUNTED as it arrives - Content-Length is a claim, and
    layer 2 of the validation ladder is the only place that claim is checked
    against reality. Reading it here and replaying it keeps that check while
    still using the public Request.form() parser rather than a private one.
    """
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


async def _read_bounded(request: Request, limit: int) -> bytes:
    """Layer 2: count the bytes actually delivered, not the ones announced."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise RequestRejectedError("request body exceeds the size limit", status=413)
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_request_part(raw: object, *, max_metadata_chars: int) -> ReconstructionRequest:
    if not isinstance(raw, str):
        raise RequestRejectedError("request part is missing or is not text")

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RequestRejectedError("request part is not valid JSON") from exc

    if not isinstance(document, dict):
        raise RequestRejectedError("request part is not a JSON object")

    # Bound the SERIALISED size. The schema bounds the property count; this
    # bounds the bytes, which is what actually costs memory and log volume, and
    # it is stricter than 16 x any per-value cap would be.
    metadata = document.get("metadata")
    if metadata is not None and (
        len(json.dumps(metadata, separators=(",", ":"))) > max_metadata_chars
    ):
        raise RequestRejectedError("request metadata exceeds the size limit")

    try:
        return ReconstructionRequest.model_validate(document)
    except ValidationError as exc:
        # The field paths are ours; the values are the caller's. Only the paths
        # go back out.
        logger.warning(
            "request part failed contract validation",
            extra={"fields": [".".join(str(p) for p in err["loc"]) for err in exc.errors()[:8]]},
        )
        raise RequestRejectedError("request part failed contract validation") from exc


async def _collect_images(
    parts: list[UploadFile],
    *,
    settings: Settings,
) -> list[Image.Image]:
    """Layers 3 to 7, for every part.

    ANY failing image rejects the WHOLE request. Silently dropping one and
    reconstructing from the rest would hide a client bug behind a plausible
    answer, which is the failure mode this service exists to avoid.
    """
    if not parts:
        raise RequestRejectedError("at least one image part is required")
    if len(parts) > settings.max_images:
        raise RequestRejectedError("too many image parts")

    prepared: list[Image.Image] = []
    for part in parts:
        data = await part.read()
        try:
            result = prepare_image(
                data,
                part.content_type,
                max_bytes=settings.max_image_bytes,
                max_pixels=settings.max_image_pixels,
                max_edge=settings.max_image_edge,
            )
        except ImageValidationError as exc:
            status = 413 if "size limit" in exc.rule else 415
            raise RequestRejectedError(exc.rule, status=status) from exc
        prepared.append(result.image)
    return prepared


def _compute(
    image: Image.Image,
    *,
    settings: Settings,
    pipeline: Reconstructor,
    longest_dimension_meters: float,
) -> _Computed:
    """The blocking half. Runs on a worker thread, never on the event loop."""
    inference_started = time.perf_counter()
    raw = pipeline.reconstruct(image)
    inference_ms = int((time.perf_counter() - inference_started) * 1000)

    mesh_started = time.perf_counter()
    normalised = normalise(
        raw.vertices,
        raw.faces,
        vertex_colors=raw.vertex_colors,
        longest_dimension_meters=longest_dimension_meters,
        smoothing_iterations=settings.mesh_smoothing_iterations,
        target_faces=settings.mesh_target_faces,
        uv=raw.uv,
        texture=raw.texture,
    )
    measurements = measure(normalised)
    glb = export_glb(normalised)
    mesh_ms = int((time.perf_counter() - mesh_started) * 1000)

    components = {
        "fieldDecisiveness": confidence.field_decisiveness(
            raw.deviation,
            band_ratio=settings.ambiguity_band_ratio,
            reference=settings.ambiguity_reference,
        ),
        "watertightness": confidence.watertightness(
            is_watertight=measurements.watertight,
            boundary_edge_ratio=measurements.boundary_edge_ratio,
        ),
        "volumePlausibility": confidence.volume_plausibility(
            measurements.volume_cubic_meters, measurements.extent
        ),
    }
    weights = confidence.ConfidenceWeights(
        field_decisiveness=settings.confidence_weight_field_decisiveness,
        watertightness=settings.confidence_weight_watertightness,
        volume_plausibility=settings.confidence_weight_volume_plausibility,
        foreground_quality=settings.confidence_weight_foreground_quality,
    )
    if raw.foreground is None:
        # No segmentation mask, so no fourth component and no weight for one.
        weights = weights.without_foreground_quality()
    else:
        components["foregroundQuality"] = confidence.foreground_quality(
            coverage=raw.foreground.coverage,
            border_fraction=raw.foreground.border_fraction,
        )

    breakdown = confidence.compose(
        components=components,
        weights=weights,
        face_count=measurements.face_count,
        min_faces=settings.min_faces,
        low_max=settings.confidence_band_low_max,
        high_min=settings.confidence_band_high_min,
        calibrated=settings.confidence_calibrated,
    )

    material_estimate = material.estimate(
        mean_vertex_color(normalised),
        volume_cubic_meters=measurements.volume_cubic_meters,
        solid_fraction=settings.solid_fraction,
    )

    return _Computed(
        glb=glb,
        measurements=measurements,
        breakdown=breakdown,
        material_estimate=material_estimate,
        seed=raw.seed,
        inference_ms=inference_ms,
        mesh_ms=mesh_ms,
    )


def _notices(
    *,
    pipeline: Reconstructor,
    computed: _Computed,
    received: int,
    used: int,
    min_faces: int,
) -> list[dict[str, str]]:
    codes: list[tuple[str, str]] = []
    if pipeline.name == "stub":
        codes.append(("stub-pipeline", "warning"))
    codes.append(("scale-assumed", "info"))
    if not computed.breakdown.calibrated:
        codes.append(("confidence-uncalibrated", "info"))
    if "foregroundQuality" not in computed.breakdown.components:
        codes.append(("foreground-quality-unavailable", "info"))
    if received > used:
        codes.append(("images-ignored", "info"))
    if computed.material_estimate.confidence < 0.5:
        codes.append(("material-weak-signal", "warning"))
    if computed.measurements.face_count < min_faces:
        codes.append(("low-face-count", "warning"))
    if not computed.measurements.watertight:
        codes.append(("mesh-not-watertight", "warning"))

    return [
        {"code": code, "severity": severity, "message": _NOTICE_TEXT[code]}
        for code, severity in codes[:_MAX_NOTICES]
    ]


@router.post(
    "/v1/reconstruct",
    response_model=ReconstructionResult,
    response_model_exclude_none=True,
    summary="Reconstruct a mesh from one to four photographs of a single object.",
)
async def reconstruct(request: Request, settings: SettingsDep) -> ReconstructionResult:
    started = time.perf_counter()
    state = request.app.state
    pipeline: Reconstructor = state.pipeline
    store: MeshStore = state.store
    lock = state.pipeline_lock

    validation_started = time.perf_counter()

    # Check the content type BEFORE reading the body. Starlette's form parser
    # returns an EMPTY FormData for a JSON body rather than raising, so without
    # this a client that posted JSON is told its `request` part is missing -
    # true, but not the thing it got wrong.
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().lstrip().startswith("multipart/form-data"):
        raise RequestRejectedError("request must be multipart/form-data", status=415)

    body = await _read_bounded(request, settings.max_request_bytes)

    replayed = StarletteRequest(request.scope, receive=_replay_receive(body))
    try:
        form = await replayed.form(
            max_files=settings.max_images + 1,
            max_fields=8,
            max_part_size=settings.max_image_bytes,
        )
    except Exception as exc:
        raise RequestRejectedError("request is not valid multipart/form-data") from exc

    try:
        document = _parse_request_part(
            form.get(_REQUEST_PART), max_metadata_chars=settings.max_metadata_chars
        )
        parts = [part for part in form.getlist(_IMAGES_PART) if isinstance(part, UploadFile)]
        images = await _collect_images(parts, settings=settings)
    finally:
        await form.close()

    validation_ms = int((time.perf_counter() - validation_started) * 1000)

    longest_dimension = (
        document.assumed_longest_dimension_meters
        if document.assumed_longest_dimension_meters is not None
        else settings.assumed_longest_dimension_meters
    )

    # The lock is the invariant; --concurrency=1 is only the current setting.
    async with lock:
        try:
            computed = await anyio.to_thread.run_sync(
                lambda: _compute(
                    images[0],
                    settings=settings,
                    pipeline=pipeline,
                    longest_dimension_meters=longest_dimension,
                )
            )
        except MeshNormalisationError as exc:
            raise RequestRejectedError(exc.rule, status=422) from exc

    request_id = document.request_id
    object_name = f"{settings.gcs_object_prefix}/{request_id}.glb"

    upload_started = time.perf_counter()
    uri = await store.put_glb(object_name=object_name, data=computed.glb)
    upload_ms = int((time.perf_counter() - upload_started) * 1000)

    measurements = computed.measurements
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "requestId": request_id,
        "completedAt": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "mesh": {
            "uri": uri,
            "format": "glb",
            "sha256": hashlib.sha256(computed.glb).hexdigest(),
            "byteLength": len(computed.glb),
            "vertexCount": measurements.vertex_count,
            "faceCount": measurements.face_count,
            "watertight": measurements.watertight,
            "extent": {
                "x": round(measurements.extent[0], 6),
                "y": round(measurements.extent[1], 6),
                "z": round(measurements.extent[2], 6),
            },
            "volumeCubicMeters": round(measurements.volume_cubic_meters, 9),
            "upAxis": "y",
            # Day 7's fiducial marker flips this to "measured" and nothing else
            # in this payload has to change.
            "scaleBasis": "assumed",
        },
        "material": {
            "name": computed.material_estimate.name,
            "basis": computed.material_estimate.basis,
            "confidence": computed.material_estimate.confidence,
            "densityKilogramsPerCubicMeter": (
                computed.material_estimate.density_kilograms_per_cubic_meter
            ),
            "massKilograms": computed.material_estimate.mass_kilograms,
            "friction": computed.material_estimate.friction,
            "restitution": computed.material_estimate.restitution,
        },
        "confidence": {
            "score": computed.breakdown.score,
            "band": computed.breakdown.band,
            "calibrated": computed.breakdown.calibrated,
            "components": computed.breakdown.components,
            "weights": computed.breakdown.weights,
        },
        "pipeline": {
            "name": pipeline.name,
            "version": pipeline.version,
            "device": pipeline.device,
            "seed": computed.seed,
        },
        "images": {
            "received": len(images),
            "accepted": len(images),
            # Day 2 reconstructs from the first image. Narrowed BEHAVIOUR
            # inside an unchanged contract, and this is where it is admitted.
            "used": 1,
            "reencoded": True,
            "longestEdgePixels": max(images[0].size),
        },
        "timings": {
            "validationMs": validation_ms,
            "inferenceMs": computed.inference_ms,
            "meshMs": computed.mesh_ms,
            "uploadMs": upload_ms,
            "totalMs": int((time.perf_counter() - started) * 1000),
        },
        "notices": _notices(
            pipeline=pipeline,
            computed=computed,
            received=len(images),
            used=1,
            min_faces=settings.min_faces,
        ),
    }

    # Validating here rather than trusting the dict: response_model would catch
    return ReconstructionResult.model_validate(payload)
