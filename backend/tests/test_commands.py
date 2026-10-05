"""Safety, authentication, priority, and lifecycle tests for simulated commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings, get_settings
from backend.app.main import create_app
from backend.app.repositories.command_repository import CommandRepository
from backend.app.repositories.device_repository import DeviceRepository


OPERATOR_TOKEN = "operator-test-token"
JETSON_TOKEN = "jetson-test-token"
OPERATOR_HEADERS = {"X-Operator-Token": OPERATOR_TOKEN}
JETSON_HEADERS = {"X-Jetson-Token": JETSON_TOKEN}


@dataclass(frozen=True)
class QueueTestContext:
    client: TestClient
    database_path: Path
    commands: CommandRepository


@pytest.fixture
def queue(tmp_path: Path) -> QueueTestContext:
    database_path = tmp_path / "commands.db"
    settings = Settings(
        app_name="Command Queue Test",
        environment="test",
        cors_origins=("http://localhost:5173",),
        log_level="WARNING",
        database_path=database_path,
        operator_api_token=OPERATOR_TOKEN,
        jetson_api_token=JETSON_TOKEN,
    )
    application = create_app(settings)
    with TestClient(application) as client:
        DeviceRepository(database_path).create(
            device_id="jetson-1",
            name="Simulated Jetson",
            transport="wifi",
        )
        yield QueueTestContext(
            client=client,
            database_path=database_path,
            commands=CommandRepository(database_path),
        )


def _request(
    command_type: str,
    payload: dict[str, object],
    *,
    request_id: UUID | None = None,
    device_id: str = "jetson-1",
    expires_in_seconds: int = 30,
) -> dict[str, object]:
    return {
        "request_id": str(request_id or uuid4()),
        "device_id": device_id,
        "command_type": command_type,
        "payload": payload,
        "expires_in_seconds": expires_in_seconds,
    }


@pytest.mark.parametrize(
    ("command_type", "payload"),
    [
        ("STOP", {}),
        ("SET_MODE", {"mode": "standby"}),
        ("SET_SPEED", {"speed_percent": 25.0}),
        ("SEND_MESSAGE", {"message": "Simulation ready"}),
    ],
)
def test_each_allowed_command_has_a_strict_valid_payload(
    queue: QueueTestContext,
    command_type: str,
    payload: dict[str, object],
) -> None:
    response = queue.client.post(
        "/api/commands",
        headers=OPERATOR_HEADERS,
        json=_request(command_type, payload),
    )

    assert response.status_code == 201
    assert response.json()["command_type"] == command_type
    assert response.json()["payload"] == payload
    assert response.json()["status"] == "pending"
    assert response.json()["simulation_only"] is True
    assert datetime.fromisoformat(response.json()["expires_at"]).tzinfo == timezone.utc


def test_full_simulated_command_lifecycle_is_recorded(queue: QueueTestContext) -> None:
    request_id = uuid4()
    created = queue.client.post(
        "/api/commands",
        headers=OPERATOR_HEADERS,
        json=_request("SET_MODE", {"mode": "manual"}, request_id=request_id),
    )
    command_id = created.json()["id"]

    listed = queue.client.get("/api/commands", headers=OPERATOR_HEADERS)
    detailed = queue.client.get(f"/api/commands/{command_id}", headers=OPERATOR_HEADERS)
    delivered = queue.client.get(
        "/api/devices/jetson-1/commands/next",
        headers=JETSON_HEADERS,
    )
    no_duplicate_delivery = queue.client.get(
        "/api/devices/jetson-1/commands/next",
        headers=JETSON_HEADERS,
    )
    running = queue.client.post(
        f"/api/commands/{command_id}/acknowledge",
        headers=JETSON_HEADERS,
        json={
            "acknowledgement_id": str(uuid4()),
            "device_id": "jetson-1",
            "status": "running",
            "result": {"simulated": True},
        },
    )
    completed = queue.client.post(
        f"/api/commands/{command_id}/acknowledge",
        headers=JETSON_HEADERS,
        json={
            "acknowledgement_id": str(uuid4()),
            "device_id": "jetson-1",
            "status": "completed",
            "result": {"message": "Simulation finished"},
        },
    )

    assert created.status_code == 201
    assert created.json()["id"] == str(request_id)
    assert listed.json()["count"] == 1
    assert detailed.json()["status"] == "pending"
    assert delivered.status_code == 200
    assert delivered.json()["id"] == command_id
    assert delivered.json()["status"] == "delivered"
    assert no_duplicate_delivery.status_code == 204
    assert running.json()["status"] == "running"
    assert completed.json()["status"] == "completed"
    assert completed.json()["result"] == {"message": "Simulation finished"}
    assert [event.status for event in queue.commands.status_history(command_id)] == [
        "pending",
        "delivered",
        "running",
        "completed",
    ]


def test_stop_has_priority_over_commands_queued_earlier(queue: QueueTestContext) -> None:
    normal = queue.client.post(
        "/api/commands",
        headers=OPERATOR_HEADERS,
        json=_request("SET_SPEED", {"speed_percent": 10.0}),
    )
    stop = queue.client.post(
        "/api/commands",
        headers=OPERATOR_HEADERS,
        json=_request("STOP", {}),
    )

    delivered = queue.client.get(
        "/api/devices/jetson-1/commands/next",
        headers=JETSON_HEADERS,
    )

    assert normal.status_code == 201
    assert stop.status_code == 201
    assert delivered.json()["id"] == stop.json()["id"]
    assert delivered.json()["command_type"] == "STOP"


@pytest.mark.parametrize(
    "body",
    [
        _request("SHELL", {"command": "shutdown"}),
        _request("STOP", {"shell": "shutdown"}),
        _request("SET_MODE", {"mode": "unrestricted"}),
        _request("SEND_MESSAGE", {"message": "valid", "executable": True}),
    ],
)
def test_unknown_or_unsafe_command_payloads_are_rejected(
    queue: QueueTestContext,
    body: dict[str, object],
) -> None:
    response = queue.client.post(
        "/api/commands",
        headers=OPERATOR_HEADERS,
        json=body,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("speed", [-0.01, 100.01])
def test_out_of_range_speed_is_rejected(
    queue: QueueTestContext,
    speed: float,
) -> None:
    response = queue.client.post(
        "/api/commands",
        headers=OPERATOR_HEADERS,
        json=_request("SET_SPEED", {"speed_percent": speed}),
    )

    assert response.status_code == 422
    assert queue.client.get("/api/commands", headers=OPERATOR_HEADERS).json()["count"] == 0


def test_duplicate_command_request_id_is_rejected(queue: QueueTestContext) -> None:
    request_id = uuid4()
    body = _request("STOP", {}, request_id=request_id)

    first = queue.client.post("/api/commands", headers=OPERATOR_HEADERS, json=body)
    duplicate = queue.client.post("/api/commands", headers=OPERATOR_HEADERS, json=body)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_command"
    assert queue.client.get("/api/commands", headers=OPERATOR_HEADERS).json()["count"] == 1


def test_expired_command_is_not_delivered_and_is_audited(queue: QueueTestContext) -> None:
    now = datetime.now(timezone.utc)
    stale = queue.commands.create(
        command_id=str(uuid4()),
        device_id="jetson-1",
        command_type="SET_SPEED",
        payload={"speed_percent": 5.0},
        created_at=now - timedelta(minutes=2),
        expires_at=now - timedelta(minutes=1),
    )

    next_command = queue.client.get(
        "/api/devices/jetson-1/commands/next",
        headers=JETSON_HEADERS,
    )
    stored = queue.client.get(f"/api/commands/{stale.id}", headers=OPERATOR_HEADERS)

    assert next_command.status_code == 204
    assert stored.json()["status"] == "expired"
    assert [event.status for event in queue.commands.status_history(stale.id)] == [
        "pending",
        "expired",
    ]


def test_duplicate_acknowledgement_is_idempotent(queue: QueueTestContext) -> None:
    created = queue.client.post(
        "/api/commands",
        headers=OPERATOR_HEADERS,
        json=_request("STOP", {}),
    )
    command_id = created.json()["id"]
    queue.client.get(
        "/api/devices/jetson-1/commands/next",
        headers=JETSON_HEADERS,
    )
    acknowledgement_id = str(uuid4())
    body = {
        "acknowledgement_id": acknowledgement_id,
        "device_id": "jetson-1",
        "status": "completed",
        "result": {"stopped": True},
    }

    first = queue.client.post(
        f"/api/commands/{command_id}/acknowledge",
        headers=JETSON_HEADERS,
        json=body,
    )
    duplicate = queue.client.post(
        f"/api/commands/{command_id}/acknowledge",
        headers=JETSON_HEADERS,
        json=body,
    )

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.json() == first.json()
    assert [event.status for event in queue.commands.status_history(command_id)] == [
        "pending",
        "delivered",
        "completed",
    ]


def test_operator_and_jetson_credentials_are_not_interchangeable(
    queue: QueueTestContext,
) -> None:
    body = _request("STOP", {})

    missing_operator = queue.client.post("/api/commands", json=body)
    jetson_as_operator = queue.client.post(
        "/api/commands",
        headers={"X-Operator-Token": JETSON_TOKEN},
        json=body,
    )
    missing_jetson = queue.client.get("/api/devices/jetson-1/commands/next")
    operator_as_jetson = queue.client.get(
        "/api/devices/jetson-1/commands/next",
        headers={"X-Jetson-Token": OPERATOR_TOKEN},
    )

    assert missing_operator.status_code == 401
    assert jetson_as_operator.status_code == 401
    assert missing_jetson.status_code == 401
    assert operator_as_jetson.status_code == 401
    assert queue.client.get("/api/commands", headers=OPERATOR_HEADERS).json()["count"] == 0


def test_pending_command_cannot_be_acknowledged_before_delivery(
    queue: QueueTestContext,
) -> None:
    created = queue.client.post(
        "/api/commands",
        headers=OPERATOR_HEADERS,
        json=_request("SEND_MESSAGE", {"message": "Hello"}),
    )

    response = queue.client.post(
        f"/api/commands/{created.json()['id']}/acknowledge",
        headers=JETSON_HEADERS,
        json={
            "acknowledgement_id": str(uuid4()),
            "device_id": "jetson-1",
            "status": "completed",
            "result": None,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_command_transition"


def test_authentication_tokens_load_from_environment_without_repr_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPERATOR_API_TOKEN", "operator-environment-secret")
    monkeypatch.setenv("JETSON_API_TOKEN", "jetson-environment-secret")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.operator_api_token == "operator-environment-secret"
    assert settings.jetson_api_token == "jetson-environment-secret"
    assert "operator-environment-secret" not in repr(settings)
    assert "jetson-environment-secret" not in repr(settings)
    get_settings.cache_clear()


def test_operator_and_jetson_tokens_cannot_be_configured_as_the_same_value() -> None:
    with pytest.raises(ValueError, match="must be different"):
        Settings(
            app_name="Unsafe Token Test",
            environment="test",
            cors_origins=("http://localhost:5173",),
            log_level="WARNING",
            database_path=Path(":memory:"),
            operator_api_token="shared-token",
            jetson_api_token="shared-token",
        )
