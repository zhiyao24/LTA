"""Independent command validation used before any handler is selected."""

import math
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Optional, Set
from uuid import UUID


ALLOWED_COMMAND_TYPES = frozenset(
    {"STOP", "SET_MODE", "SET_SPEED", "SEND_MESSAGE"}
)
ALLOWED_MODES = frozenset({"standby", "manual", "assisted"})
MIN_SPEED_PERCENT = 0.0
MAX_SPEED_PERCENT = 100.0
MAX_MESSAGE_LENGTH = 500


class CommandValidationError(ValueError):
    """Raised when a backend command is missing data or is unsafe."""


class DuplicateCommandError(CommandValidationError):
    """Raised when this agent process has already accepted a command ID."""


class ValidatedCommand:
    def __init__(self, command_id, device_id, command_type, payload, expires_at):
        self.command_id = command_id
        self.device_id = device_id
        self.command_type = command_type
        self.payload = payload
        self.expires_at = expires_at


class DuplicateTracker:
    """Keep a bounded in-memory record of commands accepted in this process."""

    def __init__(self, maximum_entries: int = 1000) -> None:
        if maximum_entries < 1:
            raise ValueError("maximum_entries must be at least 1")
        self._maximum_entries = maximum_entries
        self._ordered_ids: Deque[str] = deque()
        self._ids: Set[str] = set()

    def reject_if_duplicate(self, command_id: str) -> None:
        if command_id in self._ids:
            raise DuplicateCommandError("Command ID was already handled by this agent")

    def mark_handled(self, command_id: str) -> None:
        if command_id in self._ids:
            return
        self._ordered_ids.append(command_id)
        self._ids.add(command_id)
        while len(self._ordered_ids) > self._maximum_entries:
            removed = self._ordered_ids.popleft()
            self._ids.remove(removed)


def validate_command(
    raw_command: Any,
    *,
    expected_device_id: str,
    now: Optional[datetime] = None,
) -> ValidatedCommand:
    """Validate identity, allowlist, payload, delivery state, and expiry."""

    if not isinstance(raw_command, dict):
        raise CommandValidationError("Command response must be a JSON object")

    command_id = raw_command.get("id")
    if not isinstance(command_id, str):
        raise CommandValidationError("Command ID must be a UUID string")
    try:
        normalized_id = str(UUID(command_id))
    except (ValueError, AttributeError) as exception:
        raise CommandValidationError("Command ID must be a valid UUID") from exception
    if normalized_id != command_id.lower():
        raise CommandValidationError("Command ID must use canonical UUID formatting")

    device_id = raw_command.get("device_id")
    if device_id != expected_device_id:
        raise CommandValidationError("Command is addressed to a different device")

    if raw_command.get("status") != "delivered":
        raise CommandValidationError("Only delivered commands may be handled")
    if raw_command.get("simulation_only") is not True:
        raise CommandValidationError("Agent accepts simulation-only commands")

    command_type = raw_command.get("command_type")
    if command_type not in ALLOWED_COMMAND_TYPES:
        raise CommandValidationError("Command type is not allowlisted")

    payload = raw_command.get("payload")
    if not isinstance(payload, dict):
        raise CommandValidationError("Command payload must be a JSON object")
    validated_payload = _validate_payload(command_type, payload)

    expires_at = _parse_timestamp(raw_command.get("expires_at"), "expires_at")
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("now must include a timezone")
    if expires_at <= checked_at.astimezone(timezone.utc):
        raise CommandValidationError("Command has expired and must not be executed")

    return ValidatedCommand(
        command_id=normalized_id,
        device_id=device_id,
        command_type=command_type,
        payload=validated_payload,
        expires_at=expires_at,
    )


def _validate_payload(command_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if command_type == "STOP":
        _require_exact_keys(payload, set())
        return {}

    if command_type == "SET_MODE":
        _require_exact_keys(payload, {"mode"})
        mode = payload.get("mode")
        if mode not in ALLOWED_MODES:
            raise CommandValidationError("SET_MODE mode is not allowlisted")
        return {"mode": mode}

    if command_type == "SET_SPEED":
        _require_exact_keys(payload, {"speed_percent"})
        speed = payload.get("speed_percent")
        if isinstance(speed, bool) or not isinstance(speed, (int, float)):
            raise CommandValidationError("SET_SPEED speed_percent must be numeric")
        normalized_speed = float(speed)
        if not math.isfinite(normalized_speed):
            raise CommandValidationError("SET_SPEED speed_percent must be finite")
        if not MIN_SPEED_PERCENT <= normalized_speed <= MAX_SPEED_PERCENT:
            raise CommandValidationError("SET_SPEED speed_percent is outside 0 to 100")
        return {"speed_percent": normalized_speed}

    if command_type == "SEND_MESSAGE":
        _require_exact_keys(payload, {"message"})
        message = payload.get("message")
        if not isinstance(message, str) or not 1 <= len(message) <= MAX_MESSAGE_LENGTH:
            raise CommandValidationError("SEND_MESSAGE message must contain 1 to 500 characters")
        if any(ord(character) < 32 and character not in {"\n", "\t"} for character in message):
            raise CommandValidationError("SEND_MESSAGE message contains control characters")
        return {"message": message}

    # The allowlist check above makes this unreachable, but it keeps the helper safe
    # if a new command type is added without a corresponding payload validator.
    raise CommandValidationError("Command type has no payload validator")


def _require_exact_keys(payload: Dict[str, Any], expected: Set[str]) -> None:
    if set(payload) != expected:
        raise CommandValidationError("Command payload contains missing or unexpected fields")


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise CommandValidationError("{0} must be an ISO 8601 timestamp".format(field_name))
    try:
        if value.endswith("Z"):
            timestamp_text = value[:-1]
            offset = timezone.utc
        elif len(value) >= 6 and value[-6] in {"+", "-"} and value[-3] == ":":
            sign = 1 if value[-6] == "+" else -1
            offset_hours = int(value[-5:-3])
            offset_minutes = int(value[-2:])
            if offset_hours > 23 or offset_minutes > 59:
                raise ValueError("invalid UTC offset")
            offset = timezone(
                sign * timedelta(hours=offset_hours, minutes=offset_minutes)
            )
            timestamp_text = value[:-6]
        else:
            raise ValueError("timezone missing")
        parsed = _parse_datetime_without_offset(timestamp_text).replace(tzinfo=offset)
    except ValueError as exception:
        raise CommandValidationError(
            "{0} must be an ISO 8601 timestamp".format(field_name)
        ) from exception
    return parsed.astimezone(timezone.utc)


def _parse_datetime_without_offset(value: str) -> datetime:
    for timestamp_format in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, timestamp_format)
        except ValueError:
            continue
    raise ValueError("invalid datetime")
