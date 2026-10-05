"""Command database record."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Command:
    id: str
    device_id: str
    command_type: str
    payload: Any
    status: str
    created_at: datetime
    expires_at: datetime | None
    acknowledged_at: datetime | None
    result: Any | None


@dataclass(frozen=True)
class CommandStatusEvent:
    """One immutable status change in a command's audit history."""

    id: int
    event_id: str
    command_id: str
    status: str
    changed_at: datetime
    details: Any | None
