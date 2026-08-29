"""One named-rule error type, carried by every failure in this service."""

from __future__ import annotations

from rinne_agent.contracts.agent_job import JobActor


class RuleError(RuntimeError):
    """A named rule refused. ``rule`` is safe to return to any caller.

    retryable decides the HTTP status: only a transient failure earns a 5xx
    and another Pub/Sub delivery. Everything else is acknowledged.
    """

    def __init__(
        self,
        rule: str,
        *,
        status: int = 400,
        retryable: bool = False,
        actor: JobActor = JobActor.ingest,
    ) -> None:
        super().__init__(rule)
        self.rule = rule
        self.status = status
        self.retryable = retryable
        self.actor = actor
