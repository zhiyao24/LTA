"""Tests for the Jetson-side independent command safety boundary."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest


AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from command_validator import (  # noqa: E402
    CommandValidationError,
    DuplicateCommandError,
    DuplicateTracker,
    validate_command,
)


NOW = datetime(2026, 5, 6, 7, 8, tzinfo=timezone.utc)


def _command(command_type: str, payload: object) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "device_id": "jetson-1",
        "command_type": command_type,
        "payload": payload,
        "status": "delivered",
        "expires_at": (NOW + timedelta(seconds=30)).isoformat(),
        "simulation_only": True,
    }


@pytest.mark.parametrize(
    ("command_type", "payload"),
    [
        ("STOP", {}),
        ("SET_MODE", {"mode": "manual"}),
        ("SET_SPEED", {"speed_percent": 0}),
        ("SET_SPEED", {"speed_percent": 100.0}),
        ("SEND_MESSAGE", {"message": "Plain text only"}),
    ],
)
def test_allowlisted_commands_are_validated(
    command_type: str,
    payload: object,
) -> None:
    command = validate_command(
        _command(command_type, payload),
        expected_device_id="jetson-1",
        now=NOW,
    )

    assert command.command_type == command_type
    assert command.device_id == "jetson-1"
    assert command.expires_at.tzinfo == timezone.utc


@pytest.mark.parametrize(
    "mutator",
    [
        lambda command: command.update(id="not-a-uuid"),
        lambda command: command.update(device_id="other-device"),
        lambda command: command.update(command_type="SHELL"),
        lambda command: command.update(status="pending"),
        lambda command: command.update(simulation_only=False),
        lambda command: command.update(payload="not-an-object"),
    ],
)
def test_identity_type_delivery_and_simulation_flags_are_required(mutator) -> None:
    raw_command = _command("STOP", {})
    mutator(raw_command)

    with pytest.raises(CommandValidationError):
        validate_command(raw_command, expected_device_id="jetson-1", now=NOW)


@pytest.mark.parametrize(
    ("command_type", "payload"),
    [
        ("STOP", {"shell": "shutdown"}),
        ("SET_MODE", {"mode": "unrestricted"}),
        ("SET_MODE", {"mode": "manual", "extra": True}),
        ("SET_SPEED", {"speed_percent": -0.01}),
        ("SET_SPEED", {"speed_percent": 100.01}),
        ("SET_SPEED", {"speed_percent": True}),
        ("SET_SPEED", {"speed_percent": float("nan")}),
        ("SEND_MESSAGE", {"message": ""}),
        ("SEND_MESSAGE", {"message": "unsafe\x00text"}),
        ("SEND_MESSAGE", {"message": "valid", "command": "ignored"}),
    ],
)
def test_unsafe_or_out_of_range_payloads_are_rejected(
    command_type: str,
    payload: object,
) -> None:
    with pytest.raises(CommandValidationError):
        validate_command(
            _command(command_type, payload),
            expected_device_id="jetson-1",
            now=NOW,
        )


def test_expired_command_is_rejected() -> None:
    raw_command = _command("STOP", {})
    raw_command["expires_at"] = (NOW - timedelta(microseconds=1)).isoformat()

    with pytest.raises(CommandValidationError, match="expired"):
        validate_command(raw_command, expected_device_id="jetson-1", now=NOW)


def test_duplicate_tracker_rejects_seen_ids_and_stays_bounded() -> None:
    tracker = DuplicateTracker(maximum_entries=2)
    first, second, third = str(uuid4()), str(uuid4()), str(uuid4())

    tracker.mark_handled(first)
    tracker.mark_handled(second)
    with pytest.raises(DuplicateCommandError):
        tracker.reject_if_duplicate(first)

    tracker.mark_handled(third)

    tracker.reject_if_duplicate(first)
    with pytest.raises(DuplicateCommandError):
        tracker.reject_if_duplicate(second)
    with pytest.raises(DuplicateCommandError):
        tracker.reject_if_duplicate(third)
