"""Request scoped middleware trace correlation, body cap, security headers"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from rinne_agent.logging_setup import (
    request_id_var,
    span_id_var,
    trace_id_var,
)

logger = logging.getLogger(__name__)
Handler = Callable[[Request], Awaitable[Response]]


def _parse_cloud_trace(header: str | None) -> tuple[str | None, str | None]:
    """Parse ``X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=1``"""
    if not header:
        return None, None
    trace_part = header.split(";", 1)[0]
    if "/" in trace_part:
        trace_id, span_id = trace_part.split("/", 1)
        return (trace_id or None), (span_id or None)
    return (trace_part or None), None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Binds trace, span, and request ids for the lifetime of one request."""

    async def dispatch(self, request: Request, call_next: Handler) -> Response:
        trace_id, span_id = _parse_cloud_trace(request.headers.get("x-cloud-trace-context"))
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        trace_token = trace_id_var.set(trace_id)
        span_token = span_id_var.set(span_id)
        request_token = request_id_var.set(request_id)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            # Exactly one structured access record per request
            logger.info(
                "request handled",
                extra={
                    "httpRequest": {
                        "requestMethod": request.method,
                        "requestUrl": request.url.path,
                        "latency": f"{elapsed_ms / 1000:.6f}s",
                    },
                    "latencyMs": elapsed_ms,
                },
            )
            trace_id_var.reset(trace_token)
            span_id_var.reset(span_token)
            request_id_var.reset(request_token)

        response.headers["x-request-id"] = request_id
        return response


class BodyLimitMiddleware(BaseHTTPMiddleware):
    """Rejects oversized requests before a handler ever allocates for them."""

    def __init__(self, app: object, *, max_bytes: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Handler) -> Response:
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > self._max_bytes:
                    return JSONResponse(
                        {"error": "Request body too large"},
                        status_code=413,
                    )
            except ValueError:
                return JSONResponse({"error": "Invalid Content-Length"}, status_code=400)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Hardening headers on a JSON API."""

    async def dispatch(self, request: Request, call_next: Handler) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
        )
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        return response
