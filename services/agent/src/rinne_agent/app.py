"""Application factory."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rinne_agent.agents.identify import build_identify_agent
from rinne_agent.agents.runtime import (
    Identifier,
    Selector,
    Triager,
    build_identifier,
    build_selector,
    build_triager,
)
from rinne_agent.agents.selection import build_selection_agent
from rinne_agent.agents.triage import build_triage_agent
from rinne_agent.clients.physics import build_simulator
from rinne_agent.clients.reconstruction import build_reconstructor
from rinne_agent.config import Settings, get_settings
from rinne_agent.decide import Decider
from rinne_agent.errors import RuleError
from rinne_agent.gate import Thresholds
from rinne_agent.gcp.firestore import JobStore, build_store
from rinne_agent.gcp.objects import build_reader
from rinne_agent.gcp.tokens import MetadataTokenSource, StaticTokenSource, TokenSource
from rinne_agent.logging_setup import configure_logging, request_id_var
from rinne_agent.middleware import (
    BodyLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from rinne_agent.pipeline import Pipeline
from rinne_agent.routes import events, health, identify, jobs
from rinne_agent.scene import SolverSettings

logger = logging.getLogger(__name__)


def configure_vertex(settings: Settings) -> None:
    """google-genai reads Vertex configuration from the environment, not from a
    constructor, so the composition root sets it once and nothing else does.

    GOOGLE_GENAI_USE_VERTEXAI is what selects Vertex over the Gemini Developer
    API. Without it the client looks for GOOGLE_API_KEY, finds none, and fails
    at the first call rather than at startup - which is the wrong end of the
    deploy to discover it.
    """
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
    os.environ["GOOGLE_CLOUD_PROJECT"] = settings.gcp_project_id
    os.environ["GOOGLE_CLOUD_LOCATION"] = settings.vertex_location


def build_triage(settings: Settings) -> Triager:
    if settings.triage_mode == "flash":
        configure_vertex(settings)
    agent = (
        build_triage_agent(
            model=settings.triage_model,
            temperature=settings.triage_temperature,
            max_output_tokens=settings.selection_max_output_tokens,
            thinking_budget=settings.triage_thinking_budget,
        )
        if settings.triage_mode == "flash"
        else None
    )
    return build_triager(
        mode=settings.triage_mode,
        agent=agent,
        app_name="rinne-agent",
        model=settings.triage_model,
        timeout_seconds=settings.triage_timeout_seconds,
    )


def build_selection(settings: Settings) -> Selector:
    if settings.triage_mode == "flash":
        configure_vertex(settings)
    agent = (
        build_selection_agent(
            model=settings.triage_model,
            temperature=settings.triage_temperature,
            max_output_tokens=settings.triage_max_output_tokens,
            thinking_budget=settings.triage_thinking_budget,
        )
        if settings.triage_mode == "flash"
        else None
    )
    return build_selector(
        mode=settings.triage_mode,
        agent=agent,
        app_name="rinne-agent",
        model=settings.triage_model,
        timeout_seconds=settings.triage_timeout_seconds,
    )


def build_identify(settings: Settings) -> Identifier:
    """Same model and the same thinking budget as triage; a different question."""
    if settings.triage_mode == "flash":
        configure_vertex(settings)
    agent = (
        build_identify_agent(
            model=settings.triage_model,
            temperature=settings.triage_temperature,
            max_output_tokens=settings.selection_max_output_tokens,
            thinking_budget=settings.triage_thinking_budget,
        )
        if settings.triage_mode == "flash"
        else None
    )
    return build_identifier(
        mode=settings.triage_mode,
        agent=agent,
        app_name="rinne-agent",
        model=settings.triage_model,
        timeout_seconds=settings.triage_timeout_seconds,
    )


def build_solver(settings: Settings) -> SolverSettings:
    return SolverSettings(
        timestep_seconds=settings.solver_timestep_seconds,
        max_steps=settings.solver_max_steps,
        seed=settings.solver_seed,
        ground_friction=settings.ground_friction,
        ground_restitution=settings.ground_restitution,
        tip_force_ratio=settings.tip_force_ratio,
        tip_height_ratio=settings.tip_height_ratio,
        tip_direction_degrees=settings.tip_direction_degrees,
        tip_duration_seconds=settings.tip_duration_seconds,
        drop_height_meters=settings.drop_height_meters,
        load_multiple=settings.load_multiple,
    )


def build_tokens(settings: Settings) -> TokenSource:
    return MetadataTokenSource() if settings.is_cloud_run else StaticTokenSource()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    configure_logging(
        level=resolved.log_level,
        project_id=resolved.gcp_project_id,
        service="rinne-agent",
        version=resolved.service_version,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tokens = build_tokens(resolved)
        store: JobStore = build_store(
            mode=resolved.store_mode,
            tokens=tokens,
            project_id=resolved.gcp_project_id,
            database=resolved.firestore_database,
            collection=resolved.firestore_collection,
            timeout_seconds=resolved.firestore_timeout_seconds,
            max_attempts=resolved.firestore_max_attempts,
            backoff_seconds=resolved.firestore_backoff_seconds,
        )
        triager = build_triage(resolved)
        selector = build_selection(resolved)
        app.state.store = store
        app.state.triager = triager
        app.state.selector = selector
        app.state.identifier = build_identify(resolved)
        app.state.decider = Decider(
            selector=selector,
            reconstructor=build_reconstructor(
                mode=resolved.client_mode,
                base_url=resolved.reconstruction_service_url,
                tokens=tokens,
                timeout_seconds=resolved.reconstruction_timeout_seconds,
            ),
            simulator=build_simulator(
                mode=resolved.client_mode,
                base_url=resolved.physics_service_url,
                tokens=tokens,
                timeout_seconds=resolved.physics_timeout_seconds,
            ),
            thresholds=Thresholds(
                reconstruction_confidence=resolved.gate_reconstruction_confidence,
                material_confidence=resolved.gate_material_confidence,
            ),
            solver=build_solver(resolved),
        )
        app.state.pipeline = Pipeline(
            store=store,
            reader=build_reader(
                mode=resolved.object_mode,
                tokens=tokens,
                timeout_seconds=resolved.object_timeout_seconds,
                max_bytes=resolved.max_scan_bytes,
            ),
            triager=triager,
            decider=app.state.decider,
            max_attempts=resolved.max_attempts,
        )
        logger.info(
            "rinne-agent starting",
            extra={
                "revision": resolved.k_revision or "local",
                "region": resolved.gcp_region,
                "env": resolved.app_env,
                "store": store.mode,
                "triage": triager.model,
                "clients": resolved.client_mode,
                "scanQueue": f"gs://{resolved.scan_bucket}/{resolved.scan_prefix}",
            },
        )
        yield
        # Cloud Run sends SIGTERM and hard-kills after roughly 10 seconds.
        logger.info("rinne-agent shutting down")

    app = FastAPI(
        title="Rinne Agent",
        version=resolved.service_version,
        lifespan=lifespan,
        docs_url="/docs" if resolved.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if resolved.docs_enabled else None,
    )

    app.state.settings = resolved

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodyLimitMiddleware, max_bytes=resolved.max_request_bytes)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(jobs.router)
    app.include_router(identify.router)

    @app.exception_handler(RuleError)
    async def rule_error_handler(_request: Request, exc: RuleError) -> JSONResponse:
        """A named rule refused the request. The rule name is the whole message."""
        return JSONResponse(
            status_code=exc.status,
            content={"error": exc.rule, "requestId": request_id_var.get() or "unknown"},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Full detail to Cloud Logging, a request id to the caller.

        §12 forbids a bare try/except that swallows failure. This swallows
        nothing — exc_info=True sends the whole traceback to the log. What it
        refuses to do is put a traceback in an HTTP response, which is an
        information-disclosure bug rather than a debugging convenience.
        """
        logger.error(
            "unhandled exception",
            exc_info=exc,
            extra={"path": request.url.path, "method": request.method},
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal error", "requestId": request_id_var.get() or "unknown"},
        )

    return app
