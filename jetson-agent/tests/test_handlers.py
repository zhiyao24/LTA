"""Tests for simulation handlers and the bounded polling agent lifecycle."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from agent import JetsonAgent  # noqa: E402
from command_validator import ValidatedCommand  # noqa: E402
from config import AgentConfig, ConfigError, load_config  # noqa: E402
from handlers import HandlerError, HandlerRegistry  # noqa: E402
import http_transport  # noqa: E402
from http_transport import HttpTransport, TemporaryTransportError  # noqa: E402

from backend.app.config import Settings  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.app.repositories.device_repository import DeviceRepository  # noqa: E402


class FakeTransport:
    def __init__(
        self,
        commands: Optional[List[Dict[str, Any]]] = None,
        temporary_heartbeat_failures: int = 0,
        temporary_poll_failures: int = 0,
        temporary_ack_failures: int = 0,
    ) -> None:
        self.commands = list(commands or [])
        self.temporary_heartbeat_failures = temporary_heartbeat_failures
        self.temporary_poll_failures = temporary_poll_failures
        self.temporary_ack_failures = temporary_ack_failures
        self.poll_attempts = 0
        self.heartbeat_attempts = 0
        self.ack_attempts = 0
        self.acknowledgements: List[Dict[str, Any]] = []
        self.telemetry: List[Dict[str, Any]] = []

    def send_heartbeat(self, *, device_timestamp: str) -> Dict[str, Any]:
        self.heartbeat_attempts += 1
        if self.heartbeat_attempts <= self.temporary_heartbeat_failures:
            raise TemporaryTransportError("simulated temporary heartbeat failure")
        return {"status": "online", "device_timestamp": device_timestamp}

    def send_telemetry(
        self,
        *,
        device_timestamp: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        sample = {"device_timestamp": device_timestamp, "data": data}
        self.telemetry.append(sample)
        return sample

    def poll_next(self) -> Optional[Dict[str, Any]]:
        self.poll_attempts += 1
        if self.poll_attempts <= self.temporary_poll_failures:
            raise TemporaryTransportError("simulated temporary poll failure")
        return self.commands.pop(0) if self.commands else None

    def acknowledge(
        self,
        command_id: str,
        *,
        acknowledgement_id: str,
        status: str,
        result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        self.ack_attempts += 1
        if self.ack_attempts <= self.temporary_ack_failures:
            raise TemporaryTransportError("simulated temporary ack failure")
        acknowledgement = {
            "command_id": command_id,
            "acknowledgement_id": acknowledgement_id,
            "status": status,
            "result": result,
        }
        self.acknowledgements.append(acknowledgement)
        return acknowledgement


def _validated(command_type: str, payload: Dict[str, Any]) -> ValidatedCommand:
    return ValidatedCommand(
        command_id=str(uuid4()),
        device_id="jetson-1",
        command_type=command_type,
        payload=payload,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )


def _raw_command(
    command_type: str = "SET_SPEED",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": str(uuid4()),
        "device_id": "jetson-1",
        "command_type": command_type,
        "payload": payload if payload is not None else {"speed_percent": 20.0},
        "status": "delivered",
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
        "simulation_only": True,
    }


def _config(*, dry_run: bool = True) -> AgentConfig:
    return AgentConfig(
        backend_url="http://localhost:8000",
        device_id="jetson-1",
        device_token="test-device-token",
        poll_interval_seconds=1,
        request_timeout_seconds=1,
        dry_run=dry_run,
    )


def test_handlers_start_safe_and_never_enable_outputs() -> None:
    handlers = HandlerRegistry(dry_run=True)

    assert handlers.state.outputs_enabled is False
    assert handlers.state.stopped is True
    assert handlers.state.mode == "standby"
    assert handlers.state.speed_percent == 0

    mode_result = handlers.handle(_validated("SET_MODE", {"mode": "manual"}))
    speed_result = handlers.handle(
        _validated("SET_SPEED", {"speed_percent": 30.0})
    )

    assert mode_result["simulated"] is True
    assert speed_result["hardware_outputs_changed"] is False
    assert handlers.state.outputs_enabled is False
    assert handlers.state.speed_percent == 30.0


def test_stop_and_communication_loss_restore_safe_state() -> None:
    handlers = HandlerRegistry(dry_run=True)
    handlers.handle(_validated("SET_MODE", {"mode": "assisted"}))
    handlers.handle(_validated("SET_SPEED", {"speed_percent": 80.0}))

    stop_result = handlers.handle(_validated("STOP", {}))

    assert stop_result["action"] == "SAFE_STATE"
    assert handlers.state.outputs_enabled is False
    assert handlers.state.stopped is True
    assert handlers.state.mode == "standby"
    assert handlers.state.speed_percent == 0
    assert handlers.state.safe_state_reason == "stop_command"


def test_message_is_kept_as_inert_text(tmp_path: Path) -> None:
    target = tmp_path / "must-not-exist"
    text = "touch {0}; $(whoami)".format(target)
    handlers = HandlerRegistry(dry_run=True)

    result = handlers.handle(_validated("SEND_MESSAGE", {"message": text}))

    assert result["simulated"] is True
    assert handlers.state.last_message == text
    assert not target.exists()


def test_non_dry_run_mode_is_refused() -> None:
    with pytest.raises(HandlerError, match="real hardware handlers are not implemented"):
        HandlerRegistry(dry_run=False)

    with pytest.raises(ConfigError, match="DRY_RUN=false"):
        JetsonAgent(
            config=_config(dry_run=False),
            transport=FakeTransport(),
            handlers=HandlerRegistry(dry_run=True),
        )


def test_agent_simulates_running_and_completed_acknowledgements() -> None:
    transport = FakeTransport([_raw_command()])
    handlers = HandlerRegistry(dry_run=True)
    agent = JetsonAgent(
        config=_config(),
        transport=transport,
        handlers=handlers,
        sleep=lambda _seconds: None,
    )

    outcome = agent.run_once()

    assert outcome == "completed"
    assert [item["status"] for item in transport.acknowledgements] == [
        "running",
        "completed",
    ]
    assert transport.acknowledgements[-1]["result"]["simulated"] is True
    assert transport.heartbeat_attempts == 1
    assert len(transport.telemetry) == 1
    assert handlers.state.outputs_enabled is False


def test_lost_heartbeat_uses_bounded_backoff_and_enters_safe_state() -> None:
    sleeps: List[float] = []
    transport = FakeTransport(temporary_heartbeat_failures=10)
    handlers = HandlerRegistry(dry_run=True)
    agent = JetsonAgent(
        config=_config(),
        transport=transport,
        handlers=handlers,
        sleep=sleeps.append,
    )

    outcome = agent.run_once()

    assert outcome == "communication_lost"
    assert transport.heartbeat_attempts == 3
    assert sleeps == [0.25, 0.5]
    assert transport.poll_attempts == 0
    assert handlers.state.outputs_enabled is False
    assert handlers.state.safe_state_reason == "communication_lost"


def test_temporary_poll_failure_uses_bounded_backoff_then_safe_state() -> None:
    sleeps: List[float] = []
    transport = FakeTransport(temporary_poll_failures=10)
    handlers = HandlerRegistry(dry_run=True)
    handlers.handle(_validated("SET_SPEED", {"speed_percent": 40.0}))
    agent = JetsonAgent(
        config=_config(),
        transport=transport,
        handlers=handlers,
        sleep=sleeps.append,
    )

    outcome = agent.run_once()

    assert outcome == "communication_lost"
    assert transport.poll_attempts == 3
    assert sleeps == [0.25, 0.5]
    assert handlers.state.outputs_enabled is False
    assert handlers.state.speed_percent == 0
    assert handlers.state.safe_state_reason == "communication_lost"


def test_command_is_not_handled_when_running_acknowledgement_fails() -> None:
    transport = FakeTransport([_raw_command()], temporary_ack_failures=10)
    handlers = HandlerRegistry(dry_run=True)
    agent = JetsonAgent(
        config=_config(),
        transport=transport,
        handlers=handlers,
        sleep=lambda _seconds: None,
    )

    outcome = agent.run_once()

    assert outcome == "communication_lost"
    assert transport.ack_attempts == 3
    assert handlers.state.speed_percent == 0
    assert handlers.state.safe_state_reason == "communication_lost_before_execution"


def test_duplicate_command_is_not_handled_twice() -> None:
    command = _raw_command()
    transport = FakeTransport([command, dict(command)])
    handlers = HandlerRegistry(dry_run=True)
    agent = JetsonAgent(
        config=_config(),
        transport=transport,
        handlers=handlers,
        sleep=lambda _seconds: None,
    )

    first = agent.run_once()
    second = agent.run_once()

    assert first == "completed"
    assert second == "duplicate"
    assert handlers.state.speed_percent == 0
    assert handlers.state.safe_state_reason == "duplicate_command"


def test_dry_run_defaults_true_when_loading_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BACKEND_URL", "http://localhost:8000")
    monkeypatch.setenv("DEVICE_ID", "jetson-1")
    monkeypatch.setenv("DEVICE_TOKEN", "environment-device-token")
    monkeypatch.delenv("DRY_RUN", raising=False)

    config = load_config()

    assert config.dry_run is True
    assert "environment-device-token" not in repr(config)


def test_wifi_transport_simulation_against_local_fastapi_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real HTTP serializer through an in-process backend bridge."""

    database_path = tmp_path / "agent-backend-integration.db"
    settings = Settings(
        app_name="Agent Integration Test",
        environment="test",
        cors_origins=("http://localhost:5173",),
        log_level="WARNING",
        database_path=database_path,
        operator_api_token="integration-operator-token",
        jetson_api_token="integration-jetson-token",
    )
    application = create_app(settings)

    class BridgedResponse:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._body = body

        def read(self, maximum_bytes: int) -> bytes:
            return self._body[:maximum_bytes]

        def __enter__(self):
            return self

        def __exit__(self, _exception_type, _exception, _traceback) -> None:
            return None

    with TestClient(application) as backend_client:
        DeviceRepository(database_path).create(
            device_id="jetson-integration",
            name="In-process Jetson Simulator",
            transport="wifi",
        )
        created = backend_client.post(
            "/api/commands",
            headers={"X-Operator-Token": "integration-operator-token"},
            json={
                "request_id": str(uuid4()),
                "device_id": "jetson-integration",
                "command_type": "SET_SPEED",
                "payload": {"speed_percent": 15.0},
                "expires_in_seconds": 30,
            },
        )

        def bridge_urlopen(request, timeout):
            assert timeout == 1
            response = backend_client.request(
                request.get_method(),
                urlsplit(request.full_url).path,
                headers=dict(request.header_items()),
                content=request.data,
            )
            return BridgedResponse(response.status_code, response.content)

        monkeypatch.setattr(http_transport, "urlopen", bridge_urlopen)
        transport = HttpTransport(
            backend_url="http://local-backend.test",
            device_id="jetson-integration",
            device_token="integration-jetson-token",
            request_timeout_seconds=1,
        )
        handlers = HandlerRegistry(dry_run=True)
        outcome = JetsonAgent(
            config=AgentConfig(
                backend_url="http://local-backend.test",
                device_id="jetson-integration",
                device_token="integration-jetson-token",
                poll_interval_seconds=1,
                request_timeout_seconds=1,
                dry_run=True,
            ),
            transport=transport,
            handlers=handlers,
            sleep=lambda _seconds: None,
        ).run_once()
        stored = backend_client.get(
            "/api/commands/{0}".format(created.json()["id"]),
            headers={"X-Operator-Token": "integration-operator-token"},
        )
        devices = backend_client.get(
            "/api/devices",
            headers={"X-Operator-Token": "integration-operator-token"},
        )
        telemetry = backend_client.get(
            "/api/devices/jetson-integration/telemetry/latest",
            headers={"X-Operator-Token": "integration-operator-token"},
        )

    assert created.status_code == 201
    assert outcome == "completed"
    assert stored.json()["status"] == "completed"
    assert stored.json()["result"]["simulated"] is True
    assert devices.json()["items"][0]["status"] == "online"
    assert telemetry.json()["is_stale"] is False
    assert telemetry.json()["data"]["cpu_temperature_c"] == 44.0
    assert handlers.state.outputs_enabled is False
