"""Security regression tests for safe errors and log redaction."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


class SecretFailureService:
    def refresh(self):
        raise RuntimeError("must-not-appear-secret")


def test_unexpected_errors_do_not_leak_exception_secrets(
    tmp_path: Path,
    caplog,
) -> None:
    operator_token = "log-test-operator-token"
    application = create_app(Settings(
        app_name="Log Safety Test",
        environment="test",
        cors_origins=("http://localhost:5173",),
        log_level="ERROR",
        database_path=tmp_path / "log-safety.db",
        operator_api_token=operator_token,
    ))
    application.state.external_api_service = SecretFailureService()

    with caplog.at_level(logging.ERROR):
        with TestClient(application, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/external/refresh",
                headers={"X-Operator-Token": operator_token},
            )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_server_error"
    assert "must-not-appear-secret" not in response.text
    assert "must-not-appear-secret" not in caplog.text

