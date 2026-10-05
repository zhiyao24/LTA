"""External API snapshot database record."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ExternalApiSnapshot:
    id: int
    source: str
    received_at: datetime
    data: Any
