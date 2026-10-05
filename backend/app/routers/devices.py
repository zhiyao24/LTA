"""Authenticated heartbeat and operator device-list endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..schemas.devices import DeviceId, DeviceListResponse, DeviceResponse, HeartbeatRequest
from ..services.device_service import DeviceService
from .commands import require_jetson_auth, require_operator_auth


router = APIRouter(tags=["Devices"])


def get_device_service(request: Request) -> DeviceService:
    return request.app.state.device_service


@router.post(
    "/api/devices/{device_id}/heartbeat",
    response_model=DeviceResponse,
    dependencies=[Depends(require_jetson_auth)],
    summary="Record an authenticated Jetson heartbeat",
)
def heartbeat(
    device_id: DeviceId,
    request_body: HeartbeatRequest,
    service: DeviceService = Depends(get_device_service),
) -> DeviceResponse:
    return service.heartbeat(device_id, request_body)


@router.get(
    "/api/devices",
    response_model=DeviceListResponse,
    dependencies=[Depends(require_operator_auth)],
    summary="List devices with computed online or offline status",
)
def list_devices(
    service: DeviceService = Depends(get_device_service),
) -> DeviceListResponse:
    return service.list_devices()

