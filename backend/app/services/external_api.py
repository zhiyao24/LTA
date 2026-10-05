"""Fetch, validate, and persist data from a mock or HTTP external API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import ValidationError

from ..config import Settings
from ..models import ExternalApiSnapshot
from ..repositories.external_data_repository import ExternalDataRepository
from ..schemas.external_api import ExternalPayload


@dataclass(frozen=True)
class ExternalFetchResult:
    """Unstored data returned by one external adapter call."""

    source: str
    data: Any


class ExternalApiAdapter(Protocol):
    """Small interface that a future provider-specific adapter can implement."""

    def fetch(self) -> ExternalFetchResult:
        """Make at most one fetch attempt and return decoded response data."""


class ExternalApiError(Exception):
    """A safe error that can be returned to the frontend without leaking secrets."""

    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class MockExternalApiAdapter:
    """Deterministic local adapter used until a real provider is selected."""

    def fetch(self) -> ExternalFetchResult:
        return ExternalFetchResult(
            source="local-mock",
            data={"mock": True},
        )


class HttpExternalApiAdapter:
    """Provider-neutral JSON-over-HTTP adapter with no automatic retries."""

    def __init__(
        self,
        *,
        url: str | None,
        api_key: str | None,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._timeout = httpx.Timeout(
            connect=timeout_seconds,
            read=timeout_seconds,
            write=timeout_seconds,
            pool=timeout_seconds,
        )
        self._transport = transport

    def fetch(self) -> ExternalFetchResult:
        if not self._url:
            raise ExternalApiError(
                code="external_api_not_configured",
                message=(
                    "The external API URL is not configured. Keep mock mode enabled "
                    "or set EXTERNAL_API_URL before using HTTP mode."
                ),
                status_code=503,
            )

        headers = {"Accept": "application/json"}
        if self._api_key:
            # This generic adapter assumes Bearer authentication. Change this one
            # header when the real provider's authentication method is known.
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            with httpx.Client(
                timeout=self._timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = client.get(self._url, headers=headers)
        except httpx.TimeoutException as exception:
            raise ExternalApiError(
                code="external_api_timeout",
                message=(
                    "The external service took too long to respond. "
                    "The last valid result was kept."
                ),
                status_code=504,
            ) from exception
        except httpx.InvalidURL as exception:
            raise ExternalApiError(
                code="external_api_invalid_url",
                message="The configured external API URL is invalid.",
                status_code=503,
            ) from exception
        except httpx.RequestError as exception:
            raise ExternalApiError(
                code="external_api_connection_failed",
                message=(
                    "The backend could not connect to the external service. "
                    "The last valid result was kept."
                ),
                status_code=503,
            ) from exception

        if response.status_code in {401, 403}:
            raise ExternalApiError(
                code="external_api_authentication_failed",
                message=(
                    "The external service rejected its credentials. "
                    "Check the backend API key; the last valid result was kept."
                ),
                status_code=502,
            )
        if response.status_code == 429:
            raise ExternalApiError(
                code="external_api_rate_limited",
                message=(
                    "The external service is receiving too many requests. "
                    "Wait before refreshing again; the last valid result was kept."
                ),
                status_code=429,
            )
        if response.status_code >= 500:
            raise ExternalApiError(
                code="external_api_server_error",
                message=(
                    "The external service is currently unavailable. "
                    "The last valid result was kept."
                ),
                status_code=502,
            )
        if response.status_code >= 400:
            raise ExternalApiError(
                code="external_api_request_rejected",
                message=(
                    "The external service rejected the request. "
                    "The last valid result was kept."
                ),
                status_code=502,
            )

        try:
            data = response.json()
        except ValueError as exception:
            raise ExternalApiError(
                code="external_api_invalid_json",
                message=(
                    "The external service returned invalid JSON. "
                    "The last valid result was kept."
                ),
                status_code=502,
            ) from exception

        return ExternalFetchResult(
            source=_safe_source_name(self._url),
            data=data,
        )


class ExternalApiService:
    """Coordinate adapter calls, validation, and SQLite storage."""

    def __init__(
        self,
        *,
        adapter: ExternalApiAdapter,
        repository: ExternalDataRepository,
    ) -> None:
        self._adapter = adapter
        self._repository = repository

    def refresh(self) -> ExternalApiSnapshot:
        """Fetch once and store only after the complete payload is valid."""

        fetched = self._adapter.fetch()
        try:
            payload = ExternalPayload.model_validate(fetched.data).root
            return self._repository.create(source=fetched.source, data=payload)
        except (ValidationError, ValueError) as exception:
            raise ExternalApiError(
                code="external_api_invalid_data",
                message=(
                    "The external service returned data in an unsupported format. "
                    "The last valid result was kept."
                ),
                status_code=502,
            ) from exception

    def latest(self) -> ExternalApiSnapshot | None:
        """Return the last valid stored result without contacting the provider."""

        return self._repository.latest()


def create_external_api_service(settings: Settings) -> ExternalApiService:
    """Build the configured adapter without exposing configuration in logs."""

    repository = ExternalDataRepository(settings.database_path)
    if settings.external_api_mode == "mock":
        adapter: ExternalApiAdapter = MockExternalApiAdapter()
    else:
        adapter = HttpExternalApiAdapter(
            url=settings.external_api_url,
            api_key=settings.external_api_key,
            timeout_seconds=settings.external_api_timeout_seconds,
        )
    return ExternalApiService(adapter=adapter, repository=repository)


def _safe_source_name(url: str) -> str:
    """Remove query parameters and credentials before storing a source URL."""

    parsed = urlsplit(url)
    hostname = parsed.hostname or "configured-api"
    try:
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        port = ""
    return urlunsplit((parsed.scheme, f"{hostname}{port}", parsed.path, "", ""))
