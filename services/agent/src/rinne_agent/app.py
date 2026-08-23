"""Application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rinne_agent.config import Settings, get_settings
from rinne_agent.logging_setup import configure_logging, request_id_var
from rinne_agent.middleware import (
    BodyLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from rinne_agent.routes import health

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    configure_logging(
        level=resolved.log_level,
        project_id=resolved.gcp_project_id,
        service="rinne-agent",
        version=resolved.service_version,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "rinne-agent starting",
            extra={
                "revision": resolved.k_revision or "local",
                "region": resolved.gcp_region,
                "env": resolved.app_env,
            },
        )
        yield
        # Cloud Run sends SIGTERM and hard-kills after roughly 10 seconds.
        logger.info("rinne-agent shutting down")

    app = FastAPI(
        title="Rinne Agent",
        version=resolved.service_version,
        lifespan=lifespan,
        # No default_response_class. FastAPI 0.141 deprecated ORJSONResponse:
        # it now serialises straight to JSON bytes via Pydantic whenever a
        # return type or response_model is set, which is faster than routing
        # through a custom response class. Every route here declares
        # response_model, so this is strictly better.
        # Off in production. This service is IAM-private, but a published
        # schema is a free gift to anyone who ever finds an IAM gap.
        docs_url="/docs" if resolved.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if resolved.docs_enabled else None,
    )

    # Publish the resolved settings on the app instance so routes can depend on
    # THESE settings rather than the lru_cache'd global. Without this line the
    # `settings` parameter of create_app() is decorative: a test can pass its own
    # configuration and every route will still read the ambient environment.
    app.state.settings = resolved

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodyLimitMiddleware, max_bytes=resolved.max_request_bytes)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)

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
