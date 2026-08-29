"""The section 7 state machine, exhaustive and enforced"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from rinne_agent.contracts import AgentJob
from rinne_agent.contracts.agent_job import DecisionEntry, JobActor, JobError, JobState

TERMINAL: Final[frozenset[JobState]] = frozenset(
    {JobState.skipped_low_risk, JobState.done, JobState.failed}
)


# Transition table
_ALLOWED: Final[dict[JobState, frozenset[JobState]]] = {
    JobState.queued: frozenset({JobState.gated, JobState.triaged, JobState.skipped_low_risk}),
    JobState.gated: frozenset({JobState.triaged, JobState.skipped_low_risk}),
    JobState.triaged: frozenset({JobState.simulating}),
    JobState.simulating: frozenset({JobState.awaiting_verification, JobState.reporting}),
    JobState.awaiting_verification: frozenset({JobState.refitting}),
    JobState.refitting: frozenset({JobState.simulating}),
    JobState.reporting: frozenset({JobState.done}),
    JobState.skipped_low_risk: frozenset(),
    JobState.done: frozenset(),
    JobState.failed: frozenset(),
}

TRANSITIONS: Final[dict[JobState, frozenset[JobState]]] = {
    state: (targets if state in TERMINAL else targets | {JobState.failed})
    for state, targets in _ALLOWED.items()
}


_MISSING: list[JobState] = [state for state in JobState if state not in TRANSITIONS]
if _MISSING:  # pragma: no cover - the assertion exists so this cannot happen
    _NAMES = sorted(state.value for state in _MISSING)
    raise RuntimeError(f"state machine is missing rows for: {_NAMES}")

#: Bound from the contract. Older entries are dropped from the FRONT so the tail
#: - the most recent decisions - is what survives.
MAX_DECISIONS: Final = 24


class IllegalTransitionError(RuntimeError):
    """An edge that is not in the table. A bug, never a caller's fault."""

    def __init__(self, source: JobState, target: JobState) -> None:
        super().__init__(f"{source.value} -> {target.value} is not a legal transition")
        self.source = source
        self.target = target


def now() -> datetime:
    return datetime.now(tz=UTC)


def can_transition(source: JobState, target: JobState) -> bool:
    return target in TRANSITIONS[source]


def _appended(job: AgentJob, entry: DecisionEntry) -> list[DecisionEntry]:
    trail = [*job.decisions, entry]
    return trail[-MAX_DECISIONS:]


def transition(
    job: AgentJob,
    *,
    target: JobState,
    actor: JobActor,
    summary: str,
    model: str | None = None,
    confidence: float | None = None,
    latency_ms: int | None = None,
    at: datetime | None = None,
) -> AgentJob:
    """Return a NEW job in ``target``, or raise. Never mutates the input.

    A pure function over the document is what makes the compare-and-swap in the
    store honest: the caller holds the version it read, builds the next version,
    and the write either lands on that exact version or loses.
    """
    if not can_transition(job.state, target):
        raise IllegalTransitionError(job.state, target)

    stamp = at or now()
    entry = DecisionEntry.model_validate(
        {
            "at": stamp,
            "state": target,
            "actor": actor,
            "summary": summary[:240],
            "model": model,
            "confidence": confidence,
            "latencyMs": latency_ms,
        }
    )
    return job.model_copy(
        update={
            "state": target,
            "updated_at": stamp,
            "decisions": _appended(job, entry),
        }
    )


def fail(
    job: AgentJob,
    *,
    rule: str,
    retryable: bool,
    actor: JobActor,
    at: datetime | None = None,
) -> AgentJob:
    """Move to `failed`, recording error and lastGoodState.

    lastGoodState is the state the job was in when it broke, which is the field
    that makes a stuck job resumable instead of merely inspectable.
    """
    if job.state in TERMINAL:
        raise IllegalTransitionError(job.state, JobState.failed)

    stamp = at or now()
    last_good = job.state
    failed = transition(
        job,
        target=JobState.failed,
        actor=actor,
        summary=rule[:240],
        at=stamp,
    )
    return failed.model_copy(
        update={
            "last_good_state": last_good,
            "error": JobError.model_validate(
                {"rule": rule[:200], "at": stamp, "retryable": retryable, "actor": actor}
            ),
        }
    )
