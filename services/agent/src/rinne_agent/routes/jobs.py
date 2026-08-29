"""GET /v1/jobs/{jobId} - the decision chain, read back."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Request

from rinne_agent.contracts import AgentJob
from rinne_agent.errors import RuleError
from rinne_agent.gcp.firestore import JobStore

router = APIRouter(tags=["jobs"])

JobIdPath = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$", max_length=64)]


@router.get(
    "/v1/jobs/{job_id}",
    response_model=AgentJob,
    response_model_exclude_none=True,
    response_model_by_alias=True,
    summary="One job document, exactly as the state machine left it.",
)
async def get_job(request: Request, job_id: JobIdPath) -> AgentJob:
    store: JobStore = request.app.state.store
    found = await store.get(job_id)
    if found is None:
        raise RuleError("no job with that id", status=404)
    return found.job
