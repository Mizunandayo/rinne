"""Driving one ADK invocation and getting a typed answer back out."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Final, Protocol

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types
from pydantic import BaseModel, ValidationError

from rinne_agent.agents.identify import IdentifyOutput
from rinne_agent.agents.selection import SelectionOutput
from rinne_agent.agents.triage import TriageOutput, strip_emojis
from rinne_agent.contracts.agent_job import JobActor
from rinne_agent.errors import RuleError

logger = logging.getLogger(__name__)

_USER_ID: Final = "rinne-agent"
_MAX_RATIONALE_CHARS: Final = 280


@dataclass(frozen=True)
class Invocation:
    """What the model answered plus everything the service measured about the call."""

    raw: object
    latency_ms: int
    prompt_tokens: int | None
    response_tokens: int | None


class AdkInvoker:
    """One session per job, deleted after: InMemorySessionService is a process-lifetime dict."""

    def __init__(
        self,
        *,
        agent: LlmAgent,
        session_service: BaseSessionService,
        app_name: str,
        state_key: str,
        timeout_seconds: float,
        actor: JobActor,
    ) -> None:
        self._runner = Runner(app_name=app_name, agent=agent, session_service=session_service)
        self._sessions = session_service
        self._app_name = app_name
        self._state_key = state_key
        self._timeout_seconds = timeout_seconds
        self._actor = actor

    async def invoke(self, *, job_id: str, parts: list[types.Part]) -> Invocation:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                raw, prompt_tokens, response_tokens = await self._run(job_id, parts)
        except TimeoutError as exc:
            raise RuleError(
                "the model did not answer in time", retryable=True, actor=self._actor
            ) from exc
        except RuleError:
            raise
        # Deliberately broad. ADK raises its own wrapper types, and anything that
        # escapes here is a 500 that records nothing and strands the job in place.
        except Exception as exc:
            logger.exception("the model call failed", extra={"jobId": job_id})
            raise RuleError("the model call failed", retryable=True, actor=self._actor) from exc
        return Invocation(
            raw=raw,
            latency_ms=int((time.perf_counter() - started) * 1000),
            prompt_tokens=prompt_tokens,
            response_tokens=response_tokens,
        )

    async def _run(
        self, job_id: str, parts: list[types.Part]
    ) -> tuple[object, int | None, int | None]:
        session_id = f"{job_id}-{self._state_key}"
        await self._sessions.create_session(
            app_name=self._app_name, user_id=_USER_ID, session_id=session_id
        )
        try:
            message = types.Content(role="user", parts=parts)
            prompt_tokens: int | None = None
            response_tokens: int | None = None

            async for event in self._runner.run_async(
                user_id=_USER_ID, session_id=session_id, new_message=message
            ):
                usage = event.usage_metadata
                if usage is not None:
                    prompt_tokens = usage.prompt_token_count
                    response_tokens = usage.candidates_token_count

            session = await self._sessions.get_session(
                app_name=self._app_name, user_id=_USER_ID, session_id=session_id
            )
            state: dict[str, Any] = dict(session.state) if session is not None else {}
            raw = state.get(self._state_key)
            if raw is None:
                # Almost always an empty candidate, which on this model means the
                # thinking budget ate the answer. See config.triage_thinking_budget.
                raise RuleError("the model returned no decision", retryable=True, actor=self._actor)
            return raw, prompt_tokens, response_tokens
        finally:
            await self._sessions.delete_session(
                app_name=self._app_name, user_id=_USER_ID, session_id=session_id
            )


def _validate[T: BaseModel](model: type[T], raw: object, actor: JobActor) -> T:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        # Field paths only. The values are model output, and model output must
        # not be echoed into a log verbatim.
        logger.error(
            "model output failed validation",
            extra={"fields": [".".join(str(p) for p in e["loc"]) for e in exc.errors()[:8]]},
        )
        raise RuleError(
            "the model returned an unusable answer", retryable=False, actor=actor
        ) from exc


def _clean(text: str) -> str:
    return strip_emojis(text).strip()[:_MAX_RATIONALE_CHARS] or "No rationale given."


@dataclass(frozen=True)
class TriageOutcome:
    output: TriageOutput
    model: str
    latency_ms: int
    prompt_tokens: int | None
    response_tokens: int | None


@dataclass(frozen=True)
class SelectionOutcome:
    output: SelectionOutput
    model: str
    latency_ms: int
    prompt_tokens: int | None
    response_tokens: int | None


class Triager(Protocol):
    @property
    def model(self) -> str: ...

    async def triage(self, *, job_id: str, image: bytes, mime_type: str) -> TriageOutcome: ...


class Selector(Protocol):
    @property
    def model(self) -> str: ...

    async def select(
        self, *, job_id: str, image: bytes, mime_type: str, shape: str
    ) -> SelectionOutcome: ...


class StubTriager:
    """The test path. Selected by configuration only; nothing falls back to it."""

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


class StubSelector:
    """The test path, same rule: chosen by configuration, never as a fallback."""

    def __init__(self, *, kind: str = "tip") -> None:
        self._kind = kind

    @property
    def model(self) -> str:
        return "stub-selection"

    async def select(
        self, *, job_id: str, image: bytes, mime_type: str, shape: str
    ) -> SelectionOutcome:
        del job_id, image, mime_type, shape
        return SelectionOutcome(
            output=SelectionOutput.model_validate(
                {
                    "kind": self._kind,
                    "confidence": 0.5,
                    "rationale": "Stub selection. No model was called.",
                    "label": "stub object",
                    "longest_dimension_meters": 0.3,
                }
            ),
            model=self.model,
            latency_ms=0,
            prompt_tokens=None,
            response_tokens=1,
        )


class FlashTriager:
    def __init__(self, *, invoker: AdkInvoker, model: str) -> None:
        self._invoker = invoker
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def triage(self, *, job_id: str, image: bytes, mime_type: str) -> TriageOutcome:
        call = await self._invoker.invoke(
            job_id=job_id,
            parts=[
                types.Part.from_bytes(data=image, mime_type=mime_type),
                types.Part.from_text(text="Triage this scan for a physical stability review."),
            ],
        )
        output = _validate(TriageOutput, call.raw, JobActor.triage)
        return TriageOutcome(
            output=output.model_copy(update={"rationale": _clean(output.rationale)}),
            model=self._model,
            latency_ms=call.latency_ms,
            prompt_tokens=call.prompt_tokens,
            response_tokens=call.response_tokens,
        )


class FlashSelector:
    def __init__(self, *, invoker: AdkInvoker, model: str) -> None:
        self._invoker = invoker
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def select(
        self, *, job_id: str, image: bytes, mime_type: str, shape: str
    ) -> SelectionOutcome:
        call = await self._invoker.invoke(
            job_id=job_id,
            parts=[
                types.Part.from_bytes(data=image, mime_type=mime_type),
                types.Part.from_text(
                    text=f"Triage classified this shape as {shape}. Choose the test."
                ),
            ],
        )
        output = _validate(SelectionOutput, call.raw, JobActor.gate)
        return SelectionOutcome(
            output=output.model_copy(update={"rationale": _clean(output.rationale)}),
            model=self._model,
            latency_ms=call.latency_ms,
            prompt_tokens=call.prompt_tokens,
            response_tokens=call.response_tokens,
        )


def build_triager(
    *, mode: str, agent: LlmAgent | None, app_name: str, model: str, timeout_seconds: float
) -> Triager:
    """Selected by configuration, never by a runtime fallback."""
    if mode == "stub":
        return StubTriager()
    if agent is None:
        raise RuntimeError("triage_mode=flash requires an agent")
    return FlashTriager(
        invoker=AdkInvoker(
            agent=agent,
            session_service=InMemorySessionService(),
            app_name=app_name,
            state_key="triage",
            timeout_seconds=timeout_seconds,
            actor=JobActor.triage,
        ),
        model=model,
    )


def build_selector(
    *, mode: str, agent: LlmAgent | None, app_name: str, model: str, timeout_seconds: float
) -> Selector:
    if mode == "stub":
        return StubSelector()
    if agent is None:
        raise RuntimeError("triage_mode=flash requires an agent")
    return FlashSelector(
        invoker=AdkInvoker(
            agent=agent,
            session_service=InMemorySessionService(),
            app_name=app_name,
            state_key="selection",
            timeout_seconds=timeout_seconds,
            actor=JobActor.gate,
        ),
        model=model,
    )


@dataclass(frozen=True)
class IdentifyOutcome:
    """What the viewer route returns. Not persisted: nothing here reaches a job."""

    output: IdentifyOutput
    model: str
    latency_ms: int


class Identifier(Protocol):
    async def identify(self, *, image: bytes, mime_type: str) -> IdentifyOutcome: ...


class StubIdentifier:
    """The test path, same rule: chosen by configuration, never as a fallback."""

    async def identify(self, *, image: bytes, mime_type: str) -> IdentifyOutcome:
        del image, mime_type
        return IdentifyOutcome(
            output=IdentifyOutput.model_validate(
                {
                    "label": "stub object",
                    "longest_dimension_meters": 0.3,
                    "material": "unknown",
                    "primary": "tip",
                    "rationale": "Stub identification. No model was called.",
                }
            ),
            model="stub-identify",
            latency_ms=0,
        )


class FlashIdentifier:
    def __init__(self, *, invoker: AdkInvoker, model: str) -> None:
        self._invoker = invoker
        self._model = model

    async def identify(self, *, image: bytes, mime_type: str) -> IdentifyOutcome:
        # No job id: this is a viewer asking about a mesh, so the session is keyed
        # on the image itself rather than on a decision that does not exist.
        key = hashlib.sha256(image).hexdigest()[:16]
        call = await self._invoker.invoke(
            job_id=f"view-{key}",
            parts=[
                types.Part.from_bytes(data=image, mime_type=mime_type),
                types.Part.from_text(text="Identify this object and choose its test."),
            ],
        )
        output = _validate(IdentifyOutput, call.raw, JobActor.gate)
        return IdentifyOutcome(
            output=output.model_copy(update={"rationale": _clean(output.rationale)}),
            model=self._model,
            latency_ms=call.latency_ms,
        )


def build_identifier(
    *, mode: str, agent: LlmAgent | None, app_name: str, model: str, timeout_seconds: float
) -> Identifier:
    if mode == "stub":
        return StubIdentifier()
    if agent is None:
        raise RuntimeError("triage_mode=flash requires an agent")
    return FlashIdentifier(
        invoker=AdkInvoker(
            agent=agent,
            session_service=InMemorySessionService(),
            app_name=app_name,
            state_key="identify",
            timeout_seconds=timeout_seconds,
            actor=JobActor.gate,
        ),
        model=model,
    )
