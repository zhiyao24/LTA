"""Build status responses without performing hardware operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from ..schemas import HealthResponse, SystemStatusResponse


def utc_now() -> datetime:
    """Return an explicit timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def build_health_response() -> HealthResponse:
    """Confirm that the local FastAPI process is available."""

    return HealthResponse(
        status="ok",
        service="FastAPI backend is running",
        timestamp=utc_now(),
    )


def build_status_response(
    *,
    jetson_status: Literal["online", "offline"] = "offline",
    external_api_status: Literal["not_configured", "ready", "online", "degraded"] = "not_configured",
) -> SystemStatusResponse:
    """Return the local services summary using computed Jetson liveness."""

    return SystemStatusResponse(
        backend_status="online",
        database_status="ready",
        external_api_status=external_api_status,
        jetson_status=jetson_status,
        timestamp=utc_now(),
    )
