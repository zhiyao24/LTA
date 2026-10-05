"""Typed request and response models shared by backend routes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .external_api import ExternalPayload, ExternalSnapshotResponse
from .commands import (
    CommandAcknowledgeRequest,
    CommandCreateRequest,
    CommandListResponse,
    CommandResponse,
)


class HealthResponse(BaseModel):
    """Minimal response proving that FastAPI is running."""

    status: Literal["ok"]
    service: str
    timestamp: datetime


class SystemStatusResponse(BaseModel):
    """Current high-level state of each planned local component."""

    backend_status: Literal["online"]
    database_status: Literal["ready"]
    external_api_status: Literal["not_configured", "ready", "online", "degraded"]
    jetson_status: Literal["online", "offline"]
    timestamp: datetime


class ValidationIssue(BaseModel):
    """Safe validation detail that excludes submitted field values."""

    field: str
    message: str
    issue_type: str


class ErrorDetail(BaseModel):
    """Consistent error information returned by every error handler."""

    code: str
    message: str
    status: int
    details: list[ValidationIssue] | None = None


class ErrorResponse(BaseModel):
    """Top-level JSON error envelope."""

    error: ErrorDetail
    timestamp: datetime = Field(description="UTC time when the error response was created")


__all__ = [
    "ErrorDetail",
    "ErrorResponse",
    "CommandAcknowledgeRequest",
    "CommandCreateRequest",
    "CommandListResponse",
    "CommandResponse",
    "ExternalPayload",
    "ExternalSnapshotResponse",
    "HealthResponse",
    "SystemStatusResponse",
    "ValidationIssue",
]
