"""Mocked endpoint tests for the external API feature."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.config import Settings, get_settings
from backend.app.main import create_app
from backend.app.repositories.external_data_repository import ExternalDataRepository
from backend.app.services.external_api import ExternalApiService, HttpExternalApiAdapter


MockHandler = Callable[[httpx.Request], httpx.Response]
OPERATOR_TOKEN = "external-operator-token"
OPERATOR_HEADERS = {"X-Operator-Token": OPERATOR_TOKEN}


def _settings(database_path: Path, *, mode: str = "http") -> Settings:
    return Settings(
        app_name="External API Test",
        environment="test",
        cors_origins=("http://localhost:5173",),
        log_level="WARNING",
        database_path=database_path,
        external_api_mode=mode,
        external_api_url="https://api.example.test/data?private=query",
        external_api_key="test-backend-only-key",
        external_api_timeout_seconds=0.25,
        operator_api_token=OPERATOR_TOKEN,
    )


def _app_with_http_handler(database_path: Path, handler: MockHandler) -> FastAPI:
    settings = _settings(database_path)
    application = create_app(settings)
    application.state.external_api_service = ExternalApiService(
        adapter=HttpExternalApiAdapter(
            url=settings.external_api_url,
            api_key=settings.external_api_key,
            timeout_seconds=settings.external_api_timeout_seconds,
            transport=httpx.MockTransport(handler),
        ),
        repository=ExternalDataRepository(database_path),
    )
    return application


def test_mock_mode_refreshes_and_returns_latest_snapshot(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path / "mock.db", mode="mock"))

    with TestClient(application) as client:
        missing = client.get("/api/external/latest")
        refreshed = client.post("/api/external/refresh", headers=OPERATOR_HEADERS)
        latest = client.get("/api/external/latest")

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "external_data_not_found"
    assert refreshed.status_code == 200
    assert refreshed.json()["source"] == "local-mock"
    assert refreshed.json()["data"] == {"mock": True}
    assert latest.json() == refreshed.json()


def test_http_success_validates_stores_and_hides_credentials(tmp_path: Path) -> None:
    received_authorization: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_authorization.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"provider_defined_later": {"value": 7}})

    application = _app_with_http_handler(tmp_path / "success.db", handler)
    with TestClient(application) as client:
        response = client.post("/api/external/refresh", headers=OPERATOR_HEADERS)
        latest = client.get("/api/external/latest")

    assert response.status_code == 200
    assert response.json()["data"] == {"provider_defined_later": {"value": 7}}
    assert response.json()["source"] == "https://api.example.test/data"
    assert latest.json() == response.json()
    assert received_authorization == ["Bearer test-backend-only-key"]
    assert "test-backend-only-key" not in response.text
    assert "private=query" not in response.text


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (httpx.Response(200, content=b"not-json"), "external_api_invalid_json"),
        (httpx.Response(200, json=[1, 2, 3]), "external_api_invalid_data"),
    ],
)
def test_invalid_external_data_is_not_stored(
    tmp_path: Path,
    response: httpx.Response,
    expected_code: str,
) -> None:
    application = _app_with_http_handler(
        tmp_path / f"{expected_code}.db",
        lambda _request: response,
    )

    with TestClient(application) as client:
        refresh = client.post("/api/external/refresh", headers=OPERATOR_HEADERS)
        latest = client.get("/api/external/latest")

    assert refresh.status_code == 502
    assert refresh.json()["error"]["code"] == expected_code
    assert latest.status_code == 404


def test_timeout_returns_a_clear_error_without_retrying(tmp_path: Path) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("simulated timeout", request=request)

    application = _app_with_http_handler(tmp_path / "timeout.db", handler)
    with TestClient(application) as client:
        response = client.post("/api/external/refresh", headers=OPERATOR_HEADERS)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "external_api_timeout"
    assert "last valid result was kept" in response.json()["error"]["message"]
    assert attempts == 1


def test_authentication_error_is_safe_and_beginner_friendly(tmp_path: Path) -> None:
    application = _app_with_http_handler(
        tmp_path / "authentication.db",
        lambda _request: httpx.Response(401, json={"detail": "provider secret text"}),
    )
    with TestClient(application) as client:
        response = client.post("/api/external/refresh", headers=OPERATOR_HEADERS)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "external_api_authentication_failed"
    assert "test-backend-only-key" not in response.text
    assert "provider secret text" not in response.text


def test_rate_limit_is_reported_without_retrying(tmp_path: Path) -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, json={})

    application = _app_with_http_handler(tmp_path / "rate-limit.db", handler)
    with TestClient(application) as client:
        response = client.post("/api/external/refresh", headers=OPERATOR_HEADERS)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "external_api_rate_limited"
    assert attempts == 1


def test_server_failure_preserves_the_last_valid_result(tmp_path: Path) -> None:
    database_path = tmp_path / "server-failure.db"
    application = _app_with_http_handler(
        database_path,
        lambda _request: httpx.Response(200, json={"state": "last-valid"}),
    )

    with TestClient(application) as client:
        stored = client.post("/api/external/refresh", headers=OPERATOR_HEADERS)

        application.state.external_api_service = ExternalApiService(
            adapter=HttpExternalApiAdapter(
                url="https://api.example.test/data",
                api_key="test-backend-only-key",
                timeout_seconds=0.25,
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(503, json={})
                ),
            ),
            repository=ExternalDataRepository(database_path),
        )
        failed = client.post("/api/external/refresh", headers=OPERATOR_HEADERS)
        latest = client.get("/api/external/latest")

    assert stored.status_code == 200
    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "external_api_server_error"
    assert latest.status_code == 200
    assert latest.json() == stored.json()


def test_connection_failure_is_handled(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection failure", request=request)

    application = _app_with_http_handler(tmp_path / "connection.db", handler)
    with TestClient(application) as client:
        response = client.post("/api/external/refresh", headers=OPERATOR_HEADERS)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "external_api_connection_failed"


def test_external_api_settings_load_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXTERNAL_API_MODE", "http")
    monkeypatch.setenv("EXTERNAL_API_URL", "https://api.example.test/data")
    monkeypatch.setenv("EXTERNAL_API_KEY", "environment-only-secret")
    monkeypatch.setenv("EXTERNAL_API_TIMEOUT_SECONDS", "2.5")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.external_api_mode == "http"
    assert settings.external_api_url == "https://api.example.test/data"
    assert settings.external_api_key == "environment-only-secret"
    assert settings.external_api_timeout_seconds == 2.5
    assert "environment-only-secret" not in repr(settings)
    get_settings.cache_clear()


def test_external_refresh_requires_operator_authentication(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path / "refresh-auth.db", mode="mock"))

    with TestClient(application) as client:
        missing = client.post("/api/external/refresh")
        wrong = client.post(
            "/api/external/refresh",
            headers={"X-Operator-Token": "wrong-token"},
        )
        allowed = client.post("/api/external/refresh", headers=OPERATOR_HEADERS)

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert allowed.status_code == 200
