"""Telemetry database record."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Telemetry:
    id: int
    device_id: str
    received_at: datetime
    device_timestamp: datetime | None
    data: Any
