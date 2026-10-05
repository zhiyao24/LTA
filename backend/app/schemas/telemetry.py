"""Strict schemas for simulation-only Jetson telemetry."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


Temperature = Annotated[float, Field(ge=-40.0, le=125.0)]
Percentage = Annotated[float, Field(ge=0.0, le=100.0)]
Voltage = Annotated[float, Field(ge=0.0, le=20.0)]
SignalStrength = Annotated[float, Field(ge=-120.0, le=0.0)]


class TelemetryMetrics(BaseModel):
    """Allowlisted simulated readings; omitted readings remain missing, never zero."""

    model_config = ConfigDict(extra="forbid")

    cpu_temperature_c: Temperature | None = None
    memory_used_percent: Percentage | None = None
    supply_voltage_v: Voltage | None = None
    wifi_signal_dbm: SignalStrength | None = None

    @field_validator("*", mode="before")
    @classmethod
    def reject_boolean_readings(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("telemetry readings must be numbers")
        return value

    @field_validator("*")
    @classmethod
    def require_finite_readings(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("telemetry readings must be finite")
        return value

    @model_validator(mode="after")
    def require_one_reading(self) -> "TelemetryMetrics":
        if not self.model_fields_set or all(
            getattr(self, field_name) is None for field_name in type(self).model_fields
        ):
            raise ValueError("at least one telemetry reading is required")
        return self


class TelemetryCreateRequest(BaseModel):
    """A device timestamp plus validated readings sent by the Jetson."""

    model_config = ConfigDict(extra="forbid")

    device_timestamp: datetime
    data: TelemetryMetrics

    @field_validator("device_timestamp")
    @classmethod
    def validate_device_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("device_timestamp must include a timezone")
        return value


class TelemetryResponse(BaseModel):
    """Stored readings with backend freshness information."""

    id: int
    device_id: str
    received_at: datetime
    device_timestamp: datetime | None
    data: dict[str, JsonValue]
    is_stale: bool
    stale_after_seconds: float


class TelemetryHistoryResponse(BaseModel):
    """A bounded newest-first telemetry history response."""

    items: list[TelemetryResponse]
    count: int
    limit: int
