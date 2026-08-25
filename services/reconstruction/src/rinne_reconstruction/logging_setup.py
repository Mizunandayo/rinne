"""Structured JSON logging shaped for Google Cloud Logging"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Populated per request by middleware.py
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[str | None] = ContextVar("span_id", default=None)
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_SEVERITY = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}


# Keys LogRecord always carries. Anything else the caller passed via extra is promoted
# into the JSON payload as a structured field.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


# Never emit a value under these names, whatever the caller passes.
_REDACTED = frozenset(
    {
        "authorization",
        "token",
        "id_token",
        "access_token",
        "api_key",
        "password",
        "secret",
        "cookie",
    }
)


class CloudLoggingFormatter(logging.Formatter):
    """Formats a LogRecord as a single line of Cloud-Logging-shaped JSON."""

    def __init__(self, *, project_id: str, service: str, version: str) -> None:
        super().__init__()
        self._project_id = project_id
        self._service = service
        self._version = version

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": _SEVERITY.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "logging.googleapis.com/sourceLocation": {
                "file": record.pathname,
                "line": str(record.lineno),
                "function": record.funcName,
            },
            "serviceContext": {"service": self._service, "version": self._version},
        }

        trace_id = trace_id_var.get()
        if trace_id:
            payload["logging.googleapis.com/trace"] = (
                f"projects/{self._project_id}/traces/{trace_id}"
            )
        span_id = span_id_var.get()
        if span_id:
            payload["logging.googleapis.com/spanId"] = span_id
        request_id = request_id_var.get()
        if request_id:
            payload["requestId"] = request_id

        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = "[REDACTED]" if key.lower() in _REDACTED else value

        if record.exc_info:
            # Full traceback to Cloud Logging. It NEVER goes into an HTTP
            # response — see the exception handler in app.py.
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(*, level: str, project_id: str, service: str, version: str) -> None:
    """Install the formatter as the single root handler."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        CloudLoggingFormatter(project_id=project_id, service=service, version=version)
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn's own access log is unstructured and duplicates the middleware's
    # access record.
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    logging.getLogger("uvicorn.access").disabled = True
