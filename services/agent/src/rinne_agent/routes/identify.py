"""POST /v1/identify - what is this, and which test would tell you something.

Read-only and unpersisted. The scan page has a mesh on screen and no job behind
it, so this answers the viewer directly rather than pretending a decision was
made: nothing is written to Firestore and no state machine is entered.
"""

from __future__ import annotations

import logging
from typing import Final

from fastapi import APIRouter, Request, Response, status
from starlette.datastructures import UploadFile

from rinne_agent.errors import RuleError
from rinne_agent.gcp.objects import check_magic
from rinne_agent.routes.health import SettingsDep

logger = logging.getLogger(__name__)
router = APIRouter(tags=["identify"])

_IMAGE_PART: Final = "image"
_ALLOWED: Final = frozenset({"image/jpeg", "image/png", "image/webp"})


@router.post("/v1/identify", summary="Name the object and pick the test worth watching.")
async def identify(
    request: Request, response: Response, settings: SettingsDep
) -> dict[str, object]:
    identifier = getattr(request.app.state, "identifier", None)
    if identifier is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"error": "identification is not configured"}

    form = await request.form()
    part = form.get(_IMAGE_PART)
    if not isinstance(part, UploadFile) or part.content_type not in _ALLOWED:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"error": "one image part of type jpeg, png or webp is required"}

    image = await part.read()
    if len(image) > settings.max_scan_bytes:
        response.status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        return {"error": "the image exceeds the size limit"}

    try:
        # The declared type is a claim; the bytes are the evidence.
        check_magic(image, part.content_type)
        outcome = await identifier.identify(image=image, mime_type=part.content_type)
    except RuleError as exc:
        response.status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_400_BAD_REQUEST
        )
        return {"error": exc.rule}

    logger.info(
        "identified",
        extra={"label": outcome.output.label, "primary": outcome.output.primary},
    )
    return {
        "label": outcome.output.label,
        "longestDimensionMeters": outcome.output.longest_dimension_meters,
        "material": outcome.output.material,
        "primary": outcome.output.primary,
        "rationale": outcome.output.rationale,
        "model": outcome.model,
        "latencyMs": outcome.latency_ms,
    }
