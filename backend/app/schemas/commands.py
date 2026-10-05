"""Strict request and response models for the simulated command queue."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from ..constants.commands import (
    DEFAULT_COMMAND_EXPIRY_SECONDS,
    MAX_COMMAND_EXPIRY_SECONDS,
    MAX_MESSAGE_LENGTH,
    MAX_SPEED_PERCENT,
    MIN_COMMAND_EXPIRY_SECONDS,
    MIN_SPEED_PERCENT,
    CommandStatus,
    CommandType,
)


DeviceId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        description="Registered device ID, such as jetson-1",
    ),
]
ExpirySeconds = Annotated[
    int,
    Field(ge=MIN_COMMAND_EXPIRY_SECONDS, le=MAX_COMMAND_EXPIRY_SECONDS),
]


class StrictPayload(BaseModel):
    """Reject undeclared fields such as shell, script, or executable."""

    model_config = ConfigDict(extra="forbid")


class StopPayload(StrictPayload):
    """STOP intentionally has no configurable payload."""


class SetModePayload(StrictPayload):
    mode: Literal["standby", "manual", "assisted"]


class SetSpeedPayload(StrictPayload):
    speed_percent: Annotated[
        float,
        Field(strict=True, ge=MIN_SPEED_PERCENT, le=MAX_SPEED_PERCENT),
    ]


class SendMessagePayload(StrictPayload):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(character) < 32 and character not in {"\n", "\t"} for character in value):
            raise ValueError("message cannot contain control characters")
        return value


class BaseCommandCreate(BaseModel):
    """Fields shared by every command creation request."""

    model_config = ConfigDict(extra="forbid")

    request_id: UUID = Field(
        description="A new UUID generated once by the operator client to reject duplicate submissions"
    )
    device_id: DeviceId
    expires_in_seconds: ExpirySeconds = DEFAULT_COMMAND_EXPIRY_SECONDS


class StopCommandCreate(BaseCommandCreate):
    command_type: Literal["STOP"]
    payload: StopPayload = Field(default_factory=StopPayload)


class SetModeCommandCreate(BaseCommandCreate):
    command_type: Literal["SET_MODE"]
    payload: SetModePayload


class SetSpeedCommandCreate(BaseCommandCreate):
    command_type: Literal["SET_SPEED"]
    payload: SetSpeedPayload


class SendMessageCommandCreate(BaseCommandCreate):
    command_type: Literal["SEND_MESSAGE"]
    payload: SendMessagePayload


CommandCreateRequest = Annotated[
    StopCommandCreate
    | SetModeCommandCreate
    | SetSpeedCommandCreate
    | SendMessageCommandCreate,
    Field(discriminator="command_type"),
]


class CommandAcknowledgeRequest(BaseModel):
    """A state update sent by the simulated Jetson client."""

    model_config = ConfigDict(extra="forbid")

    acknowledgement_id: UUID = Field(
        description="A unique event ID that makes repeated acknowledgements idempotent"
    )
    device_id: DeviceId
    status: Literal["running", "completed", "failed"]
    result: dict[str, JsonValue] | None = None


class CommandResponse(BaseModel):
    """One validated command queue record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    device_id: str
    command_type: CommandType
    payload: dict[str, JsonValue]
    status: CommandStatus
    created_at: datetime
    expires_at: datetime
    acknowledged_at: datetime | None
    result: dict[str, JsonValue] | None
    simulation_only: Literal[True] = True


class CommandListResponse(BaseModel):
    """Bounded list returned to the operator dashboard."""

    items: list[CommandResponse]
    count: int
