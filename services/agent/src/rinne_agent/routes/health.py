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
async def readyz(response: Response, settings: SettingsDep) -> HealthReport:
    # Day 1 has no external dependency yet
    dependencies: list[dict[str, object]] = []
    degraded = any(dep.get("status") == "down" for dep in dependencies)

    if degraded:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthReport.model_validate(
            {**_base(settings), "status": "down", "dependencies": dependencies}
        )

    return HealthReport.model_validate(
        {**_base(settings), "status": "ok", "dependencies": dependencies}
    )
