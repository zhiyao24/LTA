"""Coordinate device liveness and bounded telemetry persistence."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from ..database import utc_now
from ..models import Device, Telemetry
from ..repositories.device_repository import DeviceRepository
from ..repositories.telemetry_repository import TelemetryRepository
from ..schemas.devices import DeviceListResponse, DeviceResponse, HeartbeatRequest
from ..schemas.telemetry import (
    TelemetryCreateRequest,
    TelemetryHistoryResponse,
    TelemetryResponse,
)


class DeviceServiceError(Exception):
    """A safe device or telemetry error suitable for a structured API response."""

    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class DeviceService:
    """Use backend receipt times for liveness, freshness, and retention."""

    def __init__(
        self,
        *,
        devices: DeviceRepository,
        telemetry: TelemetryRepository,
        heartbeat_timeout_seconds: float,
        telemetry_stale_after_seconds: float,
        telemetry_retention_hours: float,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._devices = devices
        self._telemetry = telemetry
        self._heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self._telemetry_stale_after_seconds = telemetry_stale_after_seconds
        self._telemetry_retention_hours = telemetry_retention_hours
        self._now = now

    def heartbeat(
        self,
        device_id: str,
        _request: HeartbeatRequest,
    ) -> DeviceResponse:
        """Register or refresh a device using the backend's current UTC time."""

        received_at = self._now()
        device = self._devices.record_heartbeat(device_id, received_at=received_at)
        return self._device_response(device, now=received_at)

    def list_devices(self) -> DeviceListResponse:
        """Compute online/offline status and persist any timeout transition."""

        now = self._now()
        items = [self._device_response(device, now=now) for device in self._devices.list()]
        return DeviceListResponse(items=items, count=len(items), timestamp=now)

    def receive_telemetry(
        self,
        device_id: str,
        request: TelemetryCreateRequest,
    ) -> TelemetryResponse:
        """Validate upstream, store once, update liveness, then apply retention."""

        received_at = self._now()
        self._devices.record_heartbeat(device_id, received_at=received_at)
        telemetry = self._telemetry.create(
            device_id=device_id,
            received_at=received_at,
            device_timestamp=request.device_timestamp,
            data=request.data.model_dump(exclude_none=True),
        )
        cutoff = received_at - timedelta(hours=self._telemetry_retention_hours)
        self._telemetry.delete_older_than(cutoff)
        return self._telemetry_response(telemetry, now=received_at)

    def latest_telemetry(self, device_id: str) -> TelemetryResponse:
        """Return the newest reading or a clear missing-data error."""

        self._require_device(device_id)
        telemetry = self._telemetry.latest(device_id)
        if telemetry is None:
            raise DeviceServiceError(
                code="telemetry_not_found",
                message="No telemetry has been received for this device yet.",
                status_code=404,
            )
        return self._telemetry_response(telemetry, now=self._now())

    def telemetry_history(
        self,
        device_id: str,
        *,
        limit: int,
    ) -> TelemetryHistoryResponse:
        """Return a caller-bounded newest-first history."""

        self._require_device(device_id)
        now = self._now()
        rows = self._telemetry.latest_for_device(device_id, limit=limit)
        items = [self._telemetry_response(row, now=now) for row in rows]
        return TelemetryHistoryResponse(items=items, count=len(items), limit=limit)

    def _require_device(self, device_id: str) -> Device:
        device = self._devices.get(device_id)
        if device is None:
            raise DeviceServiceError(
                code="device_not_found",
                message="The requested device has not sent a heartbeat yet.",
                status_code=404,
            )
        return device

    def _device_response(self, device: Device, *, now: datetime) -> DeviceResponse:
        cutoff = now - timedelta(seconds=self._heartbeat_timeout_seconds)
        status = (
            "online"
            if device.last_seen_at is not None and device.last_seen_at >= cutoff
            else "offline"
        )
        if device.status != status:
            updated = self._devices.update_status(
                device.id,
                status=status,
                last_seen_at=device.last_seen_at,
            )
            if updated is not None:
                device = updated
        return DeviceResponse(
            id=device.id,
            name=device.name,
            transport=device.transport,
            status=status,
            last_seen_at=device.last_seen_at,
            created_at=device.created_at,
            heartbeat_timeout_seconds=self._heartbeat_timeout_seconds,
        )

    def _telemetry_response(
        self,
        telemetry: Telemetry,
        *,
        now: datetime,
    ) -> TelemetryResponse:
        age_seconds = max(0.0, (now - telemetry.received_at).total_seconds())
        return TelemetryResponse(
            id=telemetry.id,
            device_id=telemetry.device_id,
            received_at=telemetry.received_at,
            device_timestamp=telemetry.device_timestamp,
            data=telemetry.data,
            is_stale=age_seconds > self._telemetry_stale_after_seconds,
            stale_after_seconds=self._telemetry_stale_after_seconds,
        )

