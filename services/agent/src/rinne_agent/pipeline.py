"""One delivery, one job, one decision. The whole section 7 loop, ingest to gate"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from rinne_agent.agents.runtime import Triager
from rinne_agent.contracts import AgentJob
from rinne_agent.contracts.agent_job import JobActor, JobState, TriageRecord
from rinne_agent.decide import Decider
from rinne_agent.errors import RuleError
from rinne_agent.gcp.firestore import JobStore, PreconditionFailedError, StoredJob
from rinne_agent.gcp.objects import ScanReader, check_magic
from rinne_agent.ingest import ScanEvent
from rinne_agent.state import TERMINAL, fail, now, transition

logger = logging.getLogger(__name__)

Outcome = Literal["processed", "duplicate", "failed"]


@dataclass(frozen=True)
class JobResult:
    """What the route acknowledges with."""

    outcome: Outcome
    job_id: str
    state: JobState


@dataclass(frozen=True)
class Pipeline:
    """Everything the loop needs, injected. No module-level singletons."""

    store: JobStore
    reader: ScanReader
    triager: Triager
    decider: Decider
    max_attempts: int

    async def handle(self, event: ScanEvent) -> JobResult:
        stored = await self._claim(event)
        if stored is None:
            return JobResult(outcome="duplicate", job_id=event.job_id, state=JobState.queued)

        try:
            outcome = await self._triage(stored, event)
        except RuleError as exc:
            failed = await self._record_failure(stored, exc)
            if exc.retryable:
                raise
            return JobResult(outcome="failed", job_id=event.job_id, state=failed.state)
        return outcome

    # step 1: take the job, or lose the race
    async def _claim(self, event: ScanEvent) -> StoredJob | None:
        """Create-only, then fall back to resuming a job that stalled in queued."""
        fresh = _new_job(event)
        try:
            created = await self.store.create(fresh)
        except PreconditionFailedError:
            existing = await self.store.get(event.job_id)
            if existing is None:
                return None
            if existing.job.state is not JobState.queued:
                logger.info(
                    "duplicate delivery for a job that already moved on",
                    extra={"jobId": event.job_id, "state": existing.job.state.value},
                )
                return None
            if existing.job.attempts >= self.max_attempts:
                raise RuleError(
                    "the job reached its attempt limit without completing",
                    retryable=False,
                    actor=JobActor.ingest,
                ) from None
            bumped = existing.job.model_copy(
                update={"attempts": existing.job.attempts + 1, "updated_at": now()}
            )
            try:
                return await self.store.save(bumped, expected=existing.update_time)
            except PreconditionFailedError:
                return None
        logger.info("job created", extra={"jobId": event.job_id})
        return created

    async def _triage(self, stored: StoredJob, event: ScanEvent) -> JobResult:
        image = await self.reader.read(
            bucket=event.bucket, object_name=event.object_name, generation=event.generation
        )
        check_magic(image, event.content_type)

        result = await self.triager.triage(
            job_id=event.job_id, image=image, mime_type=event.content_type
        )
        decision = result.output

        target = JobState.triaged if decision.review else JobState.skipped_low_risk
        summary = (
            "Flash decided this warrants a physics review."
            if decision.review
            else "Flash decided no physics review is needed."
        )

        record = TriageRecord.model_validate(
            {
                "review": decision.review,
                "shape": decision.shape,
                "confidence": decision.confidence,
                "rationale": decision.rationale,
                "model": result.model,
                "basis": "flash-triage-v1",
                "latencyMs": result.latency_ms,
                "promptTokens": result.prompt_tokens,
                "responseTokens": result.response_tokens,
            }
        )
        moved = transition(
            stored.job,
            target=target,
            actor=JobActor.triage,
            summary=f"{summary} Shape: {decision.shape}.",
            model=result.model,
            confidence=decision.confidence,
            latency_ms=result.latency_ms,
        ).model_copy(update={"triage": record})

        try:
            saved = await self.store.save(moved, expected=stored.update_time)
        except PreconditionFailedError:
            logger.info("lost the transition race", extra={"jobId": event.job_id})
            return JobResult(outcome="duplicate", job_id=event.job_id, state=stored.job.state)

        logger.info(
            "triage complete",
            extra={
                "jobId": event.job_id,
                "state": target.value,
                "review": decision.review,
                "shape": decision.shape,
                "model": result.model,
                "latencyMs": result.latency_ms,
            },
        )
        if target is JobState.skipped_low_risk:
            return JobResult(outcome="processed", job_id=event.job_id, state=target)
        return await self._decide(saved, event, image)

    async def _decide(self, stored: StoredJob, event: ScanEvent, image: bytes) -> JobResult:
        decided = await self.decider.decide(stored.job, image=image, mime_type=event.content_type)
        try:
            await self.store.save(decided, expected=stored.update_time)
        except PreconditionFailedError:
            logger.info("lost the decision race", extra={"jobId": event.job_id})
            return JobResult(outcome="duplicate", job_id=event.job_id, state=stored.job.state)
        return JobResult(outcome="processed", job_id=event.job_id, state=decided.state)

    # failure: reachable from any non-terminal state
    async def _record_failure(self, stored: StoredJob, exc: RuleError) -> AgentJob:
        """The caller may hold a version older than Firestore, because triage saves
        before the decision half runs. Re-read once rather than lose the error."""
        current = stored
        for final in (False, True):
            if current.job.state in TERMINAL:
                return current.job
            failed = fail(current.job, rule=exc.rule, retryable=exc.retryable, actor=exc.actor)
            try:
                await self.store.save(failed, expected=current.update_time)
            except PreconditionFailedError:
                fresh = None if final else await self.store.get(current.job.job_id)
                if fresh is None:
                    logger.info("failure not recorded; the job had already moved on")
                    return current.job
                current = fresh
                continue
            except RuleError:
                logger.error("could not record the failure", extra={"jobId": current.job.job_id})
            logger.warning(
                "job failed",
                extra={
                    "jobId": current.job.job_id,
                    "rule": exc.rule,
                    "retryable": exc.retryable,
                    "lastGoodState": current.job.state.value,
                },
            )
            return failed
        return current.job


def _new_job(event: ScanEvent) -> AgentJob:
    stamp = event.received_at
    return AgentJob.model_validate(
        {
            "schemaVersion": 1,
            "jobId": event.job_id,
            "state": JobState.queued,
            "attempts": 1,
            "createdAt": stamp,
            "updatedAt": stamp,
            "source": {
                "bucket": event.bucket,
                "object": event.object_name,
                "generation": event.generation,
                "contentType": event.content_type,
                "sizeBytes": event.size_bytes,
                "receivedAt": stamp,
                "eventId": event.event_id,
            },
            "decisions": [
                {
                    "at": stamp,
                    "state": JobState.queued,
                    "actor": JobActor.ingest,
                    "summary": "Storage event accepted; job created.",
                }
            ],
        }
    )
