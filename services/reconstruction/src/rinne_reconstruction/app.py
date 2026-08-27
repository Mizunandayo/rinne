"""Application factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rinne_reconstruction.config import Settings, get_settings
from rinne_reconstruction.logging_setup import configure_logging, request_id_var
from rinne_reconstruction.middleware import (
    BodyLimitMiddleware,
    InflightTracker,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from rinne_reconstruction.pipeline.base import Reconstructor
from rinne_reconstruction.pipeline.stub import StubReconstructor
from rinne_reconstruction.routes import health, reconstruct
from rinne_reconstruction.storage import StorageError, build_store

logger = logging.getLogger(__name__)


def build_pipeline(settings: Settings) -> Reconstructor:
    """Pick a reconstructor, and fail loudly if the chosen one cannot be built.

    There is deliberately no fallback: a TripoSR build that quietly degrades to
    the stub is exactly how a demo ends up claiming a model ran when it did
    not. Every failure below raises and the revision never receives traffic.
    """
    if settings.pipeline_name == "stub":
        return StubReconstructor(resolution=settings.stub_resolution)

    # Imported here rather than at module scope: torch and the vendored TripoSR
    # tree exist only in the GPU image, and the stub path must import without them.
    from rinne_reconstruction.pipeline.triposr import build_triposr_reconstructor

    return build_triposr_reconstructor(
        source_dir=settings.triposr_source_dir,
        weights_dir=settings.triposr_weights_dir,
        segmentation_model_path=settings.segmentation_model_path,
        commit_sha=settings.triposr_commit_sha,
        marching_cubes_resolution=settings.triposr_marching_cubes_resolution,
        chunk_size=settings.triposr_chunk_size,
        foreground_ratio=settings.triposr_foreground_ratio,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    configure_logging(
        level=resolved.log_level,
        project_id=resolved.gcp_project_id,
        service="rinne-reconstruction",
        version=resolved.service_version,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Everything expensive happens HERE, before the port is answered, so
        # the startup probe on /readyz is what gates traffic. Day 3's TripoSR
        # loads ~1.7GB of weights in this block against a hard 240-second
        # probe ceiling, which is why the weights are baked into the image.
        app.state.pipeline = build_pipeline(resolved)
        app.state.store = build_store(
            mode=resolved.storage_mode,
            bucket=resolved.gcs_bucket,
            max_attempts=resolved.upload_max_attempts,
            backoff_seconds=resolved.upload_backoff_seconds,
            timeout_seconds=resolved.upload_timeout_seconds,
        )
        logger.info(
            "rinne-reconstruction starting",
            extra={
                "revision": resolved.k_revision or "local",
                "region": resolved.gcp_region,
                "env": resolved.app_env,
                "pipeline": app.state.pipeline.name,
                "storage": app.state.store.mode,
            },
        )
        yield
        # Cloud Run sends SIGTERM and hard-kills after roughly 10 seconds.
        logger.info("rinne-reconstruction shutting down")

    app = FastAPI(
        title="Rinne Reconstruction",
        version=resolved.service_version,
        lifespan=lifespan,
        # No default_response_class. FastAPI 0.141 deprecated ORJSONResponse:
        # it now serialises straight to JSON bytes via Pydantic whenever a
        # return type or response_model is set. Every route here declares
        # response_model, so this is strictly better.
        # Docs off in production. This service is IAM-private, but a published
        # schema is a free gift to anyone who ever finds an IAM gap.
        docs_url="/docs" if resolved.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if resolved.docs_enabled else None,
    )

    # Publish the resolved settings on the app instance so routes can depend on
    # THESE settings rather than the lru_cache'd global. Without this line the
    # `settings` parameter of create_app() is decorative.
    app.state.settings = resolved

    # ONE reconstruction at a time, per instance. --concurrency=1 is the
    # deploy-time control; this is the invariant that survives someone raising
    # the flag. Created here rather than at module scope so two apps in one
    # test process do not share a lock.
    app.state.pipeline_lock = asyncio.Lock()

    # Owned here and passed in, so the gauge belongs to this app and not to
    # the process.
    inflight: dict[str, int] = {"active": 0, "peak": 0}
    app.state.inflight = inflight

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodyLimitMiddleware, max_bytes=resolved.max_request_bytes)
    app.add_middleware(InflightTracker, gauge=inflight)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(reconstruct.router)

    @app.exception_handler(reconstruct.RequestRejectedError)
    async def rejected_handler(
        _request: Request, exc: reconstruct.RequestRejectedError
    ) -> JSONResponse:
        """A named rule refused the request. The rule name is the whole message."""
        return JSONResponse(
            status_code=exc.status,
            content={"error": exc.rule, "requestId": request_id_var.get() or "unknown"},
        )

    @app.exception_handler(StorageError)
    async def storage_handler(_request: Request, exc: StorageError) -> JSONResponse:
        logger.error("storage failure", extra={"rule": exc.rule, "status": exc.status})
        return JSONResponse(
            status_code=exc.status,
            content={"error": exc.rule, "requestId": request_id_var.get() or "unknown"},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Full detail to Cloud Logging, a request id to the caller.

        Section 12 forbids a bare try/except that swallows failure. This
        swallows nothing - exc_info=True sends the whole traceback to the log.
        What it refuses to do is put a traceback in an HTTP response, which is
        an information-disclosure bug rather than a debugging convenience.
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
