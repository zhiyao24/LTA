"""HTTP endpoints for refreshing and reading external API snapshots."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..schemas.external_api import ExternalSnapshotResponse
from ..services.external_api import ExternalApiError, ExternalApiService
from .commands import require_operator_auth


router = APIRouter(prefix="/api/external", tags=["External API"])


def get_external_api_service(request: Request) -> ExternalApiService:
    """Read the application-owned service, allowing tests to replace its adapter."""

    return request.app.state.external_api_service


@router.get(
    "/latest",
    response_model=ExternalSnapshotResponse,
    summary="Read the last valid external API result",
)
def latest_external_data(
    service: ExternalApiService = Depends(get_external_api_service),
) -> ExternalSnapshotResponse:
    snapshot = service.latest()
    if snapshot is None:
        raise ExternalApiError(
            code="external_data_not_found",
            message="No valid external API result has been stored yet. Refresh it first.",
            status_code=404,
        )
    return ExternalSnapshotResponse.model_validate(snapshot)


@router.post(
    "/refresh",
    response_model=ExternalSnapshotResponse,
    dependencies=[Depends(require_operator_auth)],
    summary="Fetch and store one external API result",
)
def refresh_external_data(
    service: ExternalApiService = Depends(get_external_api_service),
) -> ExternalSnapshotResponse:
    snapshot = service.refresh()
    return ExternalSnapshotResponse.model_validate(snapshot)
