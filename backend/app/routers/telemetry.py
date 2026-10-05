"""Authenticated telemetry ingestion and bounded operator queries."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..schemas.devices import DeviceId
from ..schemas.telemetry import (
    TelemetryCreateRequest,
    TelemetryHistoryResponse,
    TelemetryResponse,
)
from ..services.device_service import DeviceService
from .commands import require_jetson_auth, require_operator_auth
from .devices import get_device_service


router = APIRouter(tags=["Telemetry"])


@router.post(
    "/api/devices/{device_id}/telemetry",
    response_model=TelemetryResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(require_jetson_auth)],
    summary="Store validated simulated telemetry",
)
def create_telemetry(
    device_id: DeviceId,
    request_body: TelemetryCreateRequest,
    service: DeviceService = Depends(get_device_service),
) -> TelemetryResponse:
    return service.receive_telemetry(device_id, request_body)


@router.get(
    "/api/devices/{device_id}/telemetry/latest",
    response_model=TelemetryResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(require_operator_auth)],
    summary="Read the latest telemetry and its freshness",
)
def latest_telemetry(
    device_id: DeviceId,
    service: DeviceService = Depends(get_device_service),
) -> TelemetryResponse:
    return service.latest_telemetry(device_id)


@router.get(
    "/api/devices/{device_id}/telemetry/history",
    response_model=TelemetryHistoryResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(require_operator_auth)],
    summary="Read a bounded newest-first telemetry history",
)
def telemetry_history(
    device_id: DeviceId,
    limit: int = Query(default=100, ge=1, le=500),
    service: DeviceService = Depends(get_device_service),
) -> TelemetryHistoryResponse:
    return service.telemetry_history(device_id, limit=limit)

