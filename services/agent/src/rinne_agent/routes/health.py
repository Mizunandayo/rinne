"""Health routes. Same two-probe split as services/physics, same contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from rinne_agent.config import Settings
from rinne_agent.contracts import HealthReport

router = APIRouter(tags=["health"])


def get_app_settings(request: Request) -> Settings:
    """Resolve settings from the app instance, not from the cached global.

    Every service must be testable in isolation. Reaching for the cached
    module-level accessor inside a handler defeats that: it is lru_cached and
    reads process environment, so configuration injected by create_app() is
    silently ignored and the factory parameter becomes decorative.
    """
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def _base(settings: Settings) -> dict[str, object]:
    payload: dict[str, object] = {
        "service": "agent",
        "version": settings.service_version,
        "checkedAt": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "region": settings.gcp_region,
    }
    if settings.k_revision:
        payload["revision"] = settings.k_revision
    return payload


@router.get(
    "/livez",
    response_model=HealthReport,
    response_model_exclude_none=True,
    summary="Liveness. Touches no dependency, so a downstream blip never causes a restart loop.",
)
async def healthz(settings: SettingsDep) -> HealthReport:
    return HealthReport.model_validate({**_base(settings), "status": "ok"})


@router.get(
    "/readyz",
    response_model=HealthReport,
    response_model_exclude_none=True,
    summary="Readiness. Returns 503 until every dependency this service needs is usable.",
)
async def readyz(request: Request, response: Response, settings: SettingsDep) -> HealthReport:
    state = request.app.state
    store = getattr(state, "store", None)
    triager = getattr(state, "triager", None)
    decider = getattr(state, "decider", None)

    dependencies: list[dict[str, object]] = [
        {
            "name": "job-store",
            "status": "ok" if store is not None else "down",
            "detail": store.mode if store is not None else "not configured",
        },
        {
            "name": "triage",
            "status": "ok" if triager is not None else "down",
            "detail": triager.model if triager is not None else "not configured",
        },
        {
            "name": "decision-loop",
            "status": "ok" if decider is not None else "down",
            "detail": f"{settings.client_mode} clients, gate "
            f"{settings.gate_reconstruction_confidence:.2f}/"
            f"{settings.gate_material_confidence:.2f}"
            if decider is not None
            else "not configured",
        },
    ]

    down = any(dep["status"] == "down" for dep in dependencies)
    if down:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthReport.model_validate(
        {
            **_base(settings),
            "status": "down" if down else "ok",
            "detail": f"scan queue gs://{settings.scan_bucket}/{settings.scan_prefix}",
            "dependencies": dependencies,
        }
    )
