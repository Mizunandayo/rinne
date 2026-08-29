"""Turning one storage delivery into one ScanEvent, or into a reasoned refusal."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from rinne_agent.contracts.agent_job import ContentType
from rinne_agent.errors import RuleError
from rinne_agent.state import now

_FINALIZED_CE_TYPE: Final = "google.cloud.storage.object.v1.finalized"
_FINALIZED_PUBSUB_TYPE: Final = "OBJECT_FINALIZE"

_ALLOWED_CONTENT_TYPES: Final[frozenset[str]] = frozenset(item.value for item in ContentType)

_ID_HEX_CHARS: Final = 16


@dataclass(frozen=True)
class ScanEvent:
    """A storage object this agent is responsible for."""

    bucket: str
    object_name: str
    generation: str
    content_type: str
    size_bytes: int
    event_id: str | None
    received_at: datetime

    @property
    def job_id(self) -> str:
        return derive_job_id(self.bucket, self.object_name, self.generation)


@dataclass(frozen=True)
class Ignored:
    """A delivery this agent will not act on. The rule says why."""

    rule: str


Delivery = ScanEvent | Ignored


def derive_job_id(bucket: str, object_name: str, generation: str) -> str:
    """Deterministic, so a redelivery maps to the SAME document.

    Generation is part of the key on purpose: re-uploading an object is a new
    scan and deserves a new job, while a duplicated delivery of one upload is
    the same job and loses the create race.
    """
    material = f"{bucket}/{object_name}#{generation}".encode()
    return f"scan-{hashlib.sha256(material).hexdigest()[:_ID_HEX_CHARS]}"


def _as_object(value: object, rule: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuleError(rule, status=400)
    return value


def _decode_body(body: bytes) -> dict[str, Any]:
    try:
        document = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuleError("delivery body is not valid JSON", status=400) from exc
    return _as_object(document, "delivery body is not a JSON object")


def _unwrap(headers: Mapping[str, str], body: bytes) -> tuple[dict[str, Any], str, str | None]:
    """Return (storage object, event type, event id) for either wire shape."""
    lowered = {key.lower(): value for key, value in headers.items()}

    ce_type = lowered.get("ce-type")
    if ce_type:
        # Binary-mode CloudEvent: the body IS the storage object resource.
        return _decode_body(body), ce_type, lowered.get("ce-id")

    document = _decode_body(body)
    message = document.get("message")
    if not isinstance(message, dict):
        raise RuleError("delivery is neither a CloudEvent nor a Pub/Sub push", status=400)

    raw = message.get("data")
    if not isinstance(raw, str):
        raise RuleError("Pub/Sub message carries no data", status=400)
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuleError("Pub/Sub message data is not valid base64", status=400) from exc

    attributes = message.get("attributes")
    attributes = attributes if isinstance(attributes, dict) else {}
    event_type = attributes.get("eventType") or attributes.get("ce-type") or ""
    event_id = message.get("messageId")

    return (
        _decode_body(decoded),
        str(event_type),
        str(event_id) if isinstance(event_id, str) else None,
    )


def _string(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key)
    return value if isinstance(value, str) else ""


def parse_delivery(
    *,
    headers: Mapping[str, str],
    body: bytes,
    bucket: str,
    prefix: str,
    max_bytes: int,
) -> Delivery:
    """Parse and vet one delivery. Raises RuleError only for a malformed request."""
    document, event_type, event_id = _unwrap(headers, body)

    if event_type not in (_FINALIZED_CE_TYPE, _FINALIZED_PUBSUB_TYPE):
        return Ignored(f"event type {event_type or 'unknown'} is not an object finalize")

    name = _string(document, "name")
    if _string(document, "bucket") != bucket:
        # Never echo the bucket that was named. It is payload.
        return Ignored("event names a bucket this agent does not watch")
    if not name.startswith(prefix):
        return Ignored("object is outside the scan queue prefix")
    if name.endswith("/"):
        return Ignored("object is a folder placeholder, not a scan")

    content_type = _string(document, "contentType")
    if content_type not in _ALLOWED_CONTENT_TYPES:
        return Ignored("object content type is not an accepted image type")

    generation = _string(document, "generation")
    if not generation.isdigit() or len(generation) > 20:
        return Ignored("object generation is missing or malformed")

    # GCS reports size as a decimal string, like generation.
    try:
        size_bytes = int(_string(document, "size") or "0")
    except ValueError:
        return Ignored("object size is missing or malformed")
    if size_bytes <= 0:
        return Ignored("object is empty")
    if size_bytes > max_bytes:
        return Ignored("object exceeds the scan size limit")

    return ScanEvent(
        bucket=bucket,
        object_name=name,
        generation=generation,
        content_type=content_type,
        size_bytes=size_bytes,
        event_id=event_id,
        received_at=now(),
    )
