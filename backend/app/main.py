"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings, get_settings
from .database import initialize_database
from .repositories.command_repository import CommandRepository
from .repositories.device_repository import DeviceRepository
from .repositories.telemetry_repository import TelemetryRepository
from .routers.commands import router as commands_router
from .routers.bus_arrivals import router as bus_arrivals_router
from .routers.devices import router as devices_router
from .routers.external_api import router as external_api_router
from .routers.status import router as status_router
from .routers.telemetry import router as telemetry_router
from .schemas import ErrorDetail, ErrorResponse, ValidationIssue
from .services.command_service import CommandService, CommandServiceError
from .services.bus_arrivals import BusArrivalService
from .services.device_service import DeviceService, DeviceServiceError
from .services.external_api import ExternalApiError, create_external_api_service


logger = logging.getLogger(__name__)


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[ValidationIssue] | None = None,
) -> JSONResponse:
    response = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            status=status_code,
            details=details,
        ),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json", exclude_none=True),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the application, allowing tests to supply isolated settings."""

    app_settings = settings or get_settings()
    logger.setLevel(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        """Prepare the local database before the API accepts requests."""

        initialize_database(app_settings.database_path)
        yield

    application = FastAPI(
        title=app_settings.app_name,
        description="Local-only status API for the Jetson Nano dashboard.",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type", "X-Operator-Token"],
    )

    application.state.settings = app_settings
    application.state.external_api_service = create_external_api_service(app_settings)
    application.state.bus_arrival_service = BusArrivalService(app_settings)
    application.state.command_service = CommandService(
        commands=CommandRepository(app_settings.database_path),
        devices=DeviceRepository(app_settings.database_path),
    )
    application.state.device_service = DeviceService(
        devices=DeviceRepository(app_settings.database_path),
        telemetry=TelemetryRepository(app_settings.database_path),
        heartbeat_timeout_seconds=app_settings.heartbeat_timeout_seconds,
        telemetry_stale_after_seconds=app_settings.telemetry_stale_after_seconds,
        telemetry_retention_hours=app_settings.telemetry_retention_hours,
    )

    application.include_router(status_router)
    application.include_router(external_api_router)
    application.include_router(bus_arrivals_router)
    application.include_router(commands_router)
    application.include_router(devices_router)
    application.include_router(telemetry_router)

    @application.exception_handler(CommandServiceError)
    async def handle_command_service_error(
        _request: Request,
        exception: CommandServiceError,
    ) -> JSONResponse:
        return _error_response(
            status_code=exception.status_code,
            code=exception.code,
            message=exception.message,
        )

    @application.exception_handler(ExternalApiError)
    async def handle_external_api_error(
        _request: Request,
        exception: ExternalApiError,
    ) -> JSONResponse:
        return _error_response(
            status_code=exception.status_code,
            code=exception.code,
            message=exception.message,
        )

    @application.exception_handler(DeviceServiceError)
    async def handle_device_service_error(
        _request: Request,
        exception: DeviceServiceError,
    ) -> JSONResponse:
        return _error_response(
            status_code=exception.status_code,
            code=exception.code,
            message=exception.message,
        )

    @application.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        _request: Request,
        exception: StarletteHTTPException,
    ) -> JSONResponse:
        error_code = {
            404: "not_found",
            405: "method_not_allowed",
        }.get(exception.status_code, "request_error")
        message = (
            exception.detail
            if isinstance(exception.detail, str)
            else "The request could not be completed."
        )
        return _error_response(
            status_code=exception.status_code,
            code=error_code,
            message=message,
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request,
        exception: RequestValidationError,
    ) -> JSONResponse:
        safe_details = [
            ValidationIssue(
                field=".".join(str(part) for part in error.get("loc", ())),
                message=str(error.get("msg", "Invalid value")),
                issue_type=str(error.get("type", "validation_error")),
            )
            for error in exception.errors()
        ]
        return _error_response(
            status_code=422,
            code="validation_error",
            message="The request contains invalid data.",
            details=safe_details,
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(
        _request: Request,
        _exception: Exception,
    ) -> JSONResponse:
        # Do not log request bodies, headers, environment variables, or exception text.
        logger.error("An unexpected backend error occurred")
        return _error_response(
            status_code=500,
            code="internal_server_error",
            message="An unexpected server error occurred.",
        )

    return application


app = create_app()
