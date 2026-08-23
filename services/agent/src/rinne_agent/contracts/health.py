# GENERATED FILE - DO NOT EDIT BY HAND.

#

# Source of truth : packages/contracts/schemas

# Regenerate      : pwsh ./packages/contracts/scripts/generate-python.ps1

#

# CI regenerates and runs git diff --exit-code. A schema edit without a

# regeneration is a build failure.

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Service(Enum):
    """
    Which Rinne service produced this report.
    """

    web = "web"
    physics = "physics"
    agent = "agent"
    reconstruction = "reconstruction"


class Status(Enum):
    """
    ok: fully serving. degraded: serving with a failed non-critical dependency. down: not serving.
    """

    ok = "ok"
    degraded = "degraded"
    down = "down"


class Status1(Enum):
    ok = "ok"
    degraded = "degraded"
    down = "down"


class Dependency(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: str = Field(..., max_length=64, min_length=1)
    status: Status1
    latency_ms: int | None = Field(None, alias="latencyMs", ge=0, le=600000)
    detail: str | None = Field(None, max_length=256)


class HealthReport(BaseModel):
    """
    Uniform liveness and readiness payload returned by every Rinne service. The web service's manifest page renders this, and smoke-test.ps1 asserts against it, so the shape is a contract and not a convenience.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    service: Service
    """
    Which Rinne service produced this report.
    """
    status: Status
    """
    ok: fully serving. degraded: serving with a failed non-critical dependency. down: not serving.
    """
    version: str = Field(..., max_length=64, min_length=1)
    """
    Build identifier. Set from the image tag at deploy time.
    """
    checked_at: datetime = Field(..., alias="checkedAt")
    """
    RFC 3339 timestamp of this check, produced at request time and never cached.
    """
    revision: str | None = Field(None, max_length=128)
    """
    Cloud Run revision name, from the K_REVISION environment variable.
    """
    region: str | None = Field(None, max_length=32)
    """
    Deployment region, for confirming the asia-southeast1 decision holds in production.
    """
    detail: str | None = Field(None, max_length=256)
    """
    Short operator-facing note. Never contains a stack trace, an internal hostname, or a credential.
    """
    dependencies: list[Dependency] | None = Field(None, max_length=16)
    """
    Downstream checks this service performed. Bounded so a compromised or buggy downstream cannot inflate a response.
    """
