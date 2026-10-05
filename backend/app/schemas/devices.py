"""Validated heartbeat requests and operator-facing device responses."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


DeviceId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]


def _timezone_aware(value: datetime | None, *, field_name: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must include a timezone")
    return value


class HeartbeatRequest(BaseModel):
    """One authenticated liveness signal from a Jetson agent."""

    model_config = ConfigDict(extra="forbid")

    device_timestamp: datetime | None = None

    @field_validator("device_timestamp")
    @classmethod
    def validate_device_timestamp(cls, value: datetime | None) -> datetime | None:
        return _timezone_aware(value, field_name="device_timestamp")


class DeviceResponse(BaseModel):
    """Device state computed from the backend receipt time of its heartbeat."""

    id: str
    name: str
    transport: str
    status: Literal["online", "offline"]
    last_seen_at: datetime | None
    created_at: datetime
    heartbeat_timeout_seconds: float


class DeviceListResponse(BaseModel):
    """All known local devices and the time used for status calculation."""

    items: list[DeviceResponse]
    count: int
    timestamp: datetime
