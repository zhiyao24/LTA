"""Authenticated HTTP routes for the simulated command queue."""

from __future__ import annotations

from secrets import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from ..constants.commands import CommandStatus
from ..schemas.commands import (
    CommandAcknowledgeRequest,
    CommandCreateRequest,
    CommandListResponse,
    CommandResponse,
)
from ..services.command_service import CommandService, CommandServiceError


router = APIRouter(tags=["Simulated Commands"])


def get_command_service(request: Request) -> CommandService:
    return request.app.state.command_service


def require_operator_auth(
    request: Request,
    supplied_token: Annotated[
        str | None,
        Header(alias="X-Operator-Token"),
    ] = None,
) -> None:
    """Authenticate frontend/operator routes with the operator-only token."""

    expected_token = request.app.state.settings.operator_api_token
    _require_role_token(
        supplied_token=supplied_token,
        expected_token=expected_token,
        role="operator",
    )


def require_jetson_auth(
    request: Request,
    supplied_token: Annotated[
        str | None,
        Header(alias="X-Jetson-Token"),
    ] = None,
) -> None:
    """Authenticate polling/acknowledgement routes with a separate device token."""

    expected_token = request.app.state.settings.jetson_api_token
    _require_role_token(
        supplied_token=supplied_token,
        expected_token=expected_token,
        role="Jetson",
    )


def _require_role_token(
    *,
    supplied_token: str | None,
    expected_token: str | None,
    role: str,
) -> None:
    if not expected_token:
        raise CommandServiceError(
            code=f"{role.lower()}_authentication_not_configured",
            message=f"{role.capitalize()} authentication is not configured on the backend.",
            status_code=503,
        )
    if supplied_token is None or not compare_digest(supplied_token, expected_token):
        raise CommandServiceError(
            code=f"{role.lower()}_unauthorized",
            message=f"A valid {role} token is required.",
            status_code=401,
        )


@router.post(
    "/api/commands",
    response_model=CommandResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator_auth)],
    summary="Queue one validated simulated command",
)
def create_command(
    request_body: CommandCreateRequest,
    service: CommandService = Depends(get_command_service),
) -> CommandResponse:
    return CommandResponse.model_validate(service.create(request_body))


@router.get(
    "/api/commands",
    response_model=CommandListResponse,
    dependencies=[Depends(require_operator_auth)],
    summary="List recent simulated commands",
)
def list_commands(
    device_id: str | None = None,
    command_status: CommandStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    service: CommandService = Depends(get_command_service),
) -> CommandListResponse:
    commands = service.list(
        device_id=device_id,
        status=command_status.value if command_status else None,
        limit=limit,
    )
    items = [CommandResponse.model_validate(command) for command in commands]
    return CommandListResponse(items=items, count=len(items))


@router.get(
    "/api/commands/{command_id}",
    response_model=CommandResponse,
    dependencies=[Depends(require_operator_auth)],
    summary="Read one simulated command",
)
def get_command(
    command_id: str,
    service: CommandService = Depends(get_command_service),
) -> CommandResponse:
    return CommandResponse.model_validate(service.get(command_id))


@router.get(
    "/api/devices/{device_id}/commands/next",
    response_model=CommandResponse,
    responses={204: {"description": "No pending command is available"}},
    dependencies=[Depends(require_jetson_auth)],
    summary="Atomically claim the next simulated command",
)
def next_device_command(
    device_id: str,
    service: CommandService = Depends(get_command_service),
) -> CommandResponse | Response:
    command = service.next_for_device(device_id)
    if command is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return CommandResponse.model_validate(command)


@router.post(
    "/api/commands/{command_id}/acknowledge",
    response_model=CommandResponse,
    dependencies=[Depends(require_jetson_auth)],
    summary="Record one simulated Jetson status update",
)
def acknowledge_command(
    command_id: str,
    request_body: CommandAcknowledgeRequest,
    service: CommandService = Depends(get_command_service),
) -> CommandResponse:
    return CommandResponse.model_validate(service.acknowledge(command_id, request_body))
