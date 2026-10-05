"""Device database record."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    transport: str
    status: str
    last_seen_at: datetime | None
    created_at: datetime
