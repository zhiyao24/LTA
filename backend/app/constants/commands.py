"""Safety limits and allowlists for simulated Jetson commands."""

from __future__ import annotations

from enum import StrEnum


class CommandType(StrEnum):
    STOP = "STOP"
    SET_MODE = "SET_MODE"
    SET_SPEED = "SET_SPEED"
    SEND_MESSAGE = "SEND_MESSAGE"


class CommandStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


ALLOWED_OPERATING_MODES = ("standby", "manual", "assisted")

# Speed is a simulated percentage, not a physical motor or vehicle unit.
MIN_SPEED_PERCENT = 0.0
MAX_SPEED_PERCENT = 100.0

DEFAULT_COMMAND_EXPIRY_SECONDS = 30
MIN_COMMAND_EXPIRY_SECONDS = 1
MAX_COMMAND_EXPIRY_SECONDS = 300
MAX_MESSAGE_LENGTH = 500

STOP_PRIORITY = 0
NORMAL_PRIORITY = 100

TERMINAL_COMMAND_STATUSES = frozenset(
    {
        CommandStatus.COMPLETED,
        CommandStatus.FAILED,
        CommandStatus.EXPIRED,
        CommandStatus.CANCELLED,
    }
)

JETSON_ACKNOWLEDGEMENT_STATUSES = frozenset(
    {
        CommandStatus.RUNNING,
        CommandStatus.COMPLETED,
        CommandStatus.FAILED,
    }
)
