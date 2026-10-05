"""Safety rules and lifecycle operations for the simulated command queue."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta

from ..constants.commands import CommandStatus
from ..database import utc_now
from ..models import Command
from ..repositories.command_repository import (
    CommandRepository,
    DuplicateStatusEventError,
    InvalidStatusTransitionError,
)
from ..repositories.device_repository import DeviceRepository
from ..schemas.commands import CommandAcknowledgeRequest, CommandCreateRequest


class CommandServiceError(Exception):
    """A safe command error suitable for a structured API response."""

    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class CommandService:
    """Apply queue rules without contacting or controlling physical hardware."""

    def __init__(
        self,
        *,
        commands: CommandRepository,
        devices: DeviceRepository,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._commands = commands
        self._devices = devices
        self._clock = clock

    def create(self, request: CommandCreateRequest) -> Command:
        """Create one expiring command after strict discriminated validation."""

        command_id = str(request.request_id)
        if self._commands.get(command_id) is not None:
            raise CommandServiceError(
                code="duplicate_command",
                message="This command request ID has already been used.",
                status_code=409,
            )
        if self._devices.get(request.device_id) is None:
            raise CommandServiceError(
                code="device_not_found",
                message="The requested device is not registered.",
                status_code=404,
            )

        created_at = self._clock()
        expires_at = created_at + timedelta(seconds=request.expires_in_seconds)
        try:
            return self._commands.create(
                command_id=command_id,
                device_id=request.device_id,
                command_type=request.command_type,
                payload=request.payload.model_dump(mode="json"),
                status=CommandStatus.PENDING.value,
                created_at=created_at,
                expires_at=expires_at,
            )
        except sqlite3.IntegrityError as exception:
            # A concurrent submission with the same UUID can reach this constraint.
            raise CommandServiceError(
                code="duplicate_command",
                message="This command request ID has already been used.",
                status_code=409,
            ) from exception

    def list(
        self,
        *,
        device_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Command]:
        self._commands.expire_stale(now=self._clock())
        return self._commands.list(device_id=device_id, status=status, limit=limit)

    def get(self, command_id: str) -> Command:
        self._commands.expire_stale(now=self._clock())
        command = self._commands.get(command_id)
        if command is None:
            raise CommandServiceError(
                code="command_not_found",
                message="The requested command does not exist.",
                status_code=404,
            )
        return command

    def next_for_device(self, device_id: str) -> Command | None:
        """Claim one command atomically; STOP is selected ahead of normal work."""

        if self._devices.get(device_id) is None:
            raise CommandServiceError(
                code="device_not_found",
                message="The requested device is not registered.",
                status_code=404,
            )
        return self._commands.claim_next_for_device(device_id, now=self._clock())

    def acknowledge(
        self,
        command_id: str,
        request: CommandAcknowledgeRequest,
    ) -> Command:
        """Apply one idempotent simulated Jetson acknowledgement."""

        self._commands.expire_stale(now=self._clock())
        command = self._commands.get(command_id)
        if command is None:
            raise CommandServiceError(
                code="command_not_found",
                message="The requested command does not exist.",
                status_code=404,
            )
        if command.device_id != request.device_id:
            raise CommandServiceError(
                code="command_device_mismatch",
                message="This command belongs to a different device.",
                status_code=403,
            )
        if command.status == CommandStatus.EXPIRED.value:
            raise CommandServiceError(
                code="command_expired",
                message="This command expired and must not be executed.",
                status_code=409,
            )

        expected_statuses = (
            (CommandStatus.DELIVERED.value,)
            if request.status == CommandStatus.RUNNING.value
            else (CommandStatus.DELIVERED.value, CommandStatus.RUNNING.value)
        )
        try:
            updated = self._commands.transition_status(
                command_id,
                expected_statuses=expected_statuses,
                status=request.status,
                event_id=str(request.acknowledgement_id),
                changed_at=self._clock(),
                result=request.result,
            )
        except DuplicateStatusEventError as exception:
            raise CommandServiceError(
                code="duplicate_acknowledgement",
                message="This acknowledgement ID was already used for another update.",
                status_code=409,
            ) from exception
        except InvalidStatusTransitionError as exception:
            raise CommandServiceError(
                code="invalid_command_transition",
                message="The command cannot move to that status from its current state.",
                status_code=409,
            ) from exception

        if updated is None:
            raise CommandServiceError(
                code="command_not_found",
                message="The requested command does not exist.",
                status_code=404,
            )
        return updated
