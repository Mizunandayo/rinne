"""POST /v1/events/scan - the bucket, through Eventarc and Pub/Sub, into the loop."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from rinne_agent.errors import RuleError
from rinne_agent.ingest import Ignored, parse_delivery
from rinne_agent.pipeline import Pipeline
from rinne_agent.routes.health import SettingsDep

logger = logging.getLogger(__name__)
router = APIRouter(tags=["events"])


class ScanEventAck(BaseModel):
    """Operational receipt for one delivery."""

    outcome: str = Field(max_length=32)
    rule: str | None = Field(default=None, max_length=200)
    job_id: str | None = Field(default=None, alias="jobId", max_length=64)
    state: str | None = Field(default=None, max_length=32)

    model_config = {"populate_by_name": True}


@router.post(
    "/v1/events/scan",
    response_model=ScanEventAck,
    response_model_exclude_none=True,
    response_model_by_alias=True,
    summary="Storage finalize events for the scan queue. Eventarc is the only caller.",
)
async def scan_event(request: Request, response: Response, settings: SettingsDep) -> ScanEventAck:
    pipeline: Pipeline = request.app.state.pipeline

    body = await request.body()
    delivery = parse_delivery(
        headers=request.headers,
        body=body,
        bucket=settings.scan_bucket,
        prefix=settings.scan_prefix,
        max_bytes=settings.max_scan_bytes,
    )

    if isinstance(delivery, Ignored):
        logger.info("delivery ignored", extra={"rule": delivery.rule})
        return ScanEventAck(outcome="ignored", rule=delivery.rule)

    try:
        result = await pipeline.handle(delivery)
    except RuleError as exc:
        if not exc.retryable:
            logger.error("delivery permanently refused", extra={"rule": exc.rule})
            return ScanEventAck(outcome="refused", rule=exc.rule, jobId=delivery.job_id)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ScanEventAck(outcome="retry", rule=exc.rule, jobId=delivery.job_id)

    return ScanEventAck(outcome=result.outcome, jobId=result.job_id, state=result.state.value)
