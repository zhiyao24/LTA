"""Tests for health, status, CORS, and structured errors."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings, get_settings
from backend.app.main import create_app


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_name="Test Jetson API",
        environment="test",
        cors_origins=(
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ),
        log_level="WARNING",
        database_path=tmp_path / "status.db",
    )


def test_health_confirms_fastapi_is_running(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "FastAPI backend is running"
    assert datetime.fromisoformat(body["timestamp"]).tzinfo == timezone.utc


def test_status_returns_all_planned_component_states(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "backend_status",
        "database_status",
        "external_api_status",
        "jetson_status",
        "timestamp",
    }
    assert body["backend_status"] == "online"
    assert body["database_status"] == "ready"
    assert body["external_api_status"] == "not_configured"
    assert body["jetson_status"] == "offline"
    assert datetime.fromisoformat(body["timestamp"]).tzinfo == timezone.utc


def test_cors_allows_only_a_configured_frontend_origin(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        allowed = client.options(
            "/api/status",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        unlisted = client.options(
            "/api/status",
            headers={
                "Origin": "http://unlisted.local:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in unlisted.headers


def test_unknown_route_returns_a_structured_error(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == {
        "code": "not_found",
        "message": "Not Found",
        "status": 404,
    }
    assert datetime.fromisoformat(body["timestamp"]).tzinfo == timezone.utc


def test_settings_are_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_NAME", "Environment Test API")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173,http://panel.local:4173")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("DATABASE_PATH", "backend/data/test-settings.db")
    monkeypatch.setenv("JETSON_HEARTBEAT_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("TELEMETRY_STALE_AFTER_SECONDS", "20")
    monkeypatch.setenv("TELEMETRY_RETENTION_HOURS", "48")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.app_name == "Environment Test API"
    assert settings.environment == "test"
    assert settings.cors_origins == (
        "http://localhost:5173",
        "http://panel.local:4173",
    )
    assert settings.log_level == "DEBUG"
    assert settings.database_path.name == "test-settings.db"
    assert settings.heartbeat_timeout_seconds == 12
    assert settings.telemetry_stale_after_seconds == 20
    assert settings.telemetry_retention_hours == 48
    get_settings.cache_clear()


def test_wildcard_cors_origin_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "*")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="wildcards are not allowed"):
        get_settings()

    get_settings.cache_clear()
