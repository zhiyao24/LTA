"""Health and system-status HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import HealthResponse, SystemStatusResponse
from ..services.status_service import build_health_response, build_status_response


router = APIRouter(tags=["Status"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check that FastAPI is running",
)
def health() -> HealthResponse:
    return build_health_response()


@router.get(
    "/api/status",
    response_model=SystemStatusResponse,
    summary="Read the local system status",
)
def system_status(request: Request) -> SystemStatusResponse:
    devices = request.app.state.device_service.list_devices()
    jetson_status = (
        "online"
        if any(device.status == "online" for device in devices.items)
        else "offline"
    )
    return build_status_response(
        jetson_status=jetson_status,
        external_api_status=request.app.state.bus_arrival_service.status,
    )
