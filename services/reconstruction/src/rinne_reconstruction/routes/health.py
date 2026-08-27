"""Health routes. Same two-probe split as the other services, same contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from rinne_reconstruction.config import Settings
from rinne_reconstruction.contracts import HealthReport

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
        "service": "reconstruction",
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
async def livez(settings: SettingsDep) -> HealthReport:
    # Cheap ON PURPOSE. Cloud Run probes this every 30 seconds, and it has to
    # answer while a reconstruction is occupying a worker thread. Anything that
    # takes the pipeline lock here would turn a slow request into a restart.
    return HealthReport.model_validate({**_base(settings), "status": "ok"})


@router.get(
    "/readyz",
    response_model=HealthReport,
    response_model_exclude_none=True,
    summary="Readiness. Returns 503 until every dependency this service needs is usable.",
)
async def readyz(request: Request, response: Response, settings: SettingsDep) -> HealthReport:
    state = request.app.state
    pipeline = getattr(state, "pipeline", None)
    store = getattr(state, "store", None)
    gauge: dict[str, int] = state.inflight

    dependencies: list[dict[str, object]] = [
        {
            "name": "pipeline",
            "status": "ok" if pipeline is not None else "down",
            "detail": f"{pipeline.name} {pipeline.version} on {pipeline.device}"
            if pipeline is not None
            else "not loaded",
        },
        {
            "name": "storage",
            "status": "ok" if store is not None else "down",
            "detail": store.mode if store is not None else "not configured",
        },
    ]

    down = any(dep["status"] == "down" for dep in dependencies)
    if down:
        # The startup probe polls this path, so a revision whose pipeline never
        # loaded never receives traffic.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthReport.model_validate(
        {
            **_base(settings),
            "status": "down" if down else "ok",
            # The gauge belongs here rather than in a dependency entry: it is a
            # property of this instance, not of something downstream.
            "detail": f"{gauge['active']} in flight, peak {gauge['peak']}",
            "dependencies": dependencies,
        }
    )
