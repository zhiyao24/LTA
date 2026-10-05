"""Complete laptop-only command flow through FastAPI and the real agent serializer."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.repositories.command_repository import CommandRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = PROJECT_ROOT / "jetson-agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import http_transport  # noqa: E402
from agent import JetsonAgent  # noqa: E402
from config import AgentConfig  # noqa: E402
from handlers import HandlerRegistry  # noqa: E402
from http_transport import HttpTransport  # noqa: E402


class BridgedResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self, maximum_bytes: int) -> bytes:
        return self._body[:maximum_bytes]

    def __enter__(self) -> "BridgedResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_complete_simulated_command_flow(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "complete-simulation.db"
    operator_token = "e2e-operator-token"
    jetson_token = "e2e-jetson-token"
    device_id = "jetson-e2e"
    settings = Settings(
        app_name="Complete Simulation Test",
        environment="test",
        cors_origins=("http://localhost:5173",),
        log_level="WARNING",
        database_path=database_path,
        external_api_mode="mock",
        operator_api_token=operator_token,
        jetson_api_token=jetson_token,
    )
    application = create_app(settings)

    with TestClient(application) as backend:
        def bridge_urlopen(request, timeout):
            parsed = urlsplit(request.full_url)
            path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            response = backend.request(
                request.get_method(),
                path,
                headers=dict(request.header_items()),
                content=request.data,
            )
            return BridgedResponse(response.status_code, response.content)

        monkeypatch.setattr(http_transport, "urlopen", bridge_urlopen)
        transport = HttpTransport(
            backend_url="http://in-process-backend.test",
            device_id=device_id,
            device_token=jetson_token,
            request_timeout_seconds=1,
        )
        handlers = HandlerRegistry(dry_run=True)
        agent = JetsonAgent(
            config=AgentConfig(
                backend_url="http://in-process-backend.test",
                device_id=device_id,
                device_token=jetson_token,
                poll_interval_seconds=1,
                request_timeout_seconds=1,
                dry_run=True,
            ),
            transport=transport,
            handlers=handlers,
            sleep=lambda _seconds: None,
        )

        assert backend.get("/health").status_code == 200
        assert agent.run_once() == "idle"

        operator_headers = {"X-Operator-Token": operator_token}
        refreshed = backend.post("/api/external/refresh", headers=operator_headers)
        created = backend.post(
            "/api/commands",
            headers=operator_headers,
            json={
                "request_id": str(uuid4()),
                "device_id": device_id,
                "command_type": "SET_SPEED",
                "payload": {"speed_percent": 15.0},
                "expires_in_seconds": 30,
            },
        )

        assert refreshed.status_code == 200
        assert created.status_code == 201
        assert created.json()["status"] == "pending"
        assert agent.run_once() == "completed"

        command_id = created.json()["id"]
        stored = backend.get(
            f"/api/commands/{command_id}",
            headers=operator_headers,
        )
        device = backend.get("/api/devices", headers=operator_headers)
        telemetry = backend.get(
            f"/api/devices/{device_id}/telemetry/latest",
            headers=operator_headers,
        )

    assert stored.json()["status"] == "completed"
    assert stored.json()["result"]["simulated"] is True
    assert device.json()["items"][0]["status"] == "online"
    assert telemetry.json()["is_stale"] is False
    assert handlers.state.outputs_enabled is False
    assert [
        event.status for event in CommandRepository(database_path).status_history(command_id)
    ] == ["pending", "delivered", "running", "completed"]

