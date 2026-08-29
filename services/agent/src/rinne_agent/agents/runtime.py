"""Driving one ADK invocation and getting a typed answer back out."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Final, Protocol

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from rinne_agent.agents.triage import TriageOutput, strip_emojis
from rinne_agent.contracts.agent_job import JobActor
from rinne_agent.errors import RuleError

logger = logging.getLogger(__name__)

_USER_ID: Final = "rinne-agent"
_STATE_KEY: Final = "triage"
_MAX_RATIONALE_CHARS: Final = 280


@dataclass(frozen=True)
class TriageOutcome:
    """The model's answer plus everything the service measured about the call."""

    output: TriageOutput
    model: str
    latency_ms: int
    prompt_tokens: int | None
    response_tokens: int | None


class Triager(Protocol):
    """Two implementations: Flash through ADK, and a deterministic stub."""

    @property
    def model(self) -> str: ...

    async def triage(self, *, job_id: str, image: bytes, mime_type: str) -> TriageOutcome: ...


class StubTriager:
    """The test path. Deterministic, offline, and honest about being a stub"""

    def __init__(self, *, review: bool = True, shape: str = "tall-narrow") -> None:
        self._review = review
        self._shape = shape

    @property
    def model(self) -> str:
        return "stub-triage"

    async def triage(self, *, job_id: str, image: bytes, mime_type: str) -> TriageOutcome:
        del job_id, mime_type
        return TriageOutcome(
            output=TriageOutput.model_validate(
                {
                    "review": self._review,
                    "shape": self._shape,
                    "confidence": 0.5,
                    "rationale": "Stub triage. No model was called.",
                }
            ),
            model=self.model,
            latency_ms=0,
            prompt_tokens=None,
            response_tokens=max(1, len(image) // 1024),
        )


class FlashTriager:
    """Section 7 step 1, through the Agent Development Kit."""

    def __init__(
        self,
        *,
        agent: LlmAgent,
        session_service: BaseSessionService,
        app_name: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self._runner = Runner(app_name=app_name, agent=agent, session_service=session_service)
        self._sessions = session_service
        self._app_name = app_name
        self._model = model
        self._timeout_seconds = timeout_seconds

    @property
    def model(self) -> str:
        return self._model

    async def triage(self, *, job_id: str, image: bytes, mime_type: str) -> TriageOutcome:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                raw, prompt_tokens, response_tokens = await self._invoke(job_id, image, mime_type)
        except TimeoutError as exc:
            raise RuleError(
                "the triage model did not answer in time",
                retryable=True,
                actor=JobActor.triage,
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        try:
            output = TriageOutput.model_validate(raw)
        except ValidationError as exc:
            logger.error(
                "triage output failed validation",
                extra={"fields": [".".join(str(p) for p in e["loc"]) for e in exc.errors()[:8]]},
            )
            raise RuleError(
                "the triage model returned an unusable answer",
                retryable=False,
                actor=JobActor.triage,
            ) from exc

        cleaned = strip_emojis(output.rationale).strip()[:_MAX_RATIONALE_CHARS]
        return TriageOutcome(
            output=output.model_copy(update={"rationale": cleaned or "No rationale given."}),
            model=self._model,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            response_tokens=response_tokens,
        )

    async def _invoke(
        self, job_id: str, image: bytes, mime_type: str
    ) -> tuple[object, int | None, int | None]:
        await self._sessions.create_session(
            app_name=self._app_name, user_id=_USER_ID, session_id=job_id
        )
        try:
            message = types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=image, mime_type=mime_type),
                    types.Part.from_text(text="Triage this scan for a physical stability review."),
                ],
            )
            prompt_tokens: int | None = None
            response_tokens: int | None = None

            async for event in self._runner.run_async(
                user_id=_USER_ID, session_id=job_id, new_message=message
            ):
                usage = event.usage_metadata
                if usage is not None:
                    prompt_tokens = usage.prompt_token_count
                    response_tokens = usage.candidates_token_count

            session = await self._sessions.get_session(
                app_name=self._app_name, user_id=_USER_ID, session_id=job_id
            )
            state: dict[str, Any] = dict(session.state) if session is not None else {}
            raw = state.get(_STATE_KEY)
            if raw is None:
                raise RuleError(
                    "the triage model returned no decision",
                    retryable=True,
                    actor=JobActor.triage,
                )
            return raw, prompt_tokens, response_tokens
        finally:
            await self._sessions.delete_session(
                app_name=self._app_name, user_id=_USER_ID, session_id=job_id
            )


def build_triager(
    *,
    mode: str,
    agent: LlmAgent | None,
    app_name: str,
    model: str,
    timeout_seconds: float,
) -> Triager:
    """Selected by configuration, never by a runtime fallback."""
    if mode == "stub":
        return StubTriager()
    if agent is None:
        raise RuntimeError("triage_mode=flash requires an agent")
    return FlashTriager(
        agent=agent,
        session_service=InMemorySessionService(),
        app_name=app_name,
        model=model,
        timeout_seconds=timeout_seconds,
    )
