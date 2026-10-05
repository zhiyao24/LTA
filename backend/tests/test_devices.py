"""Tests for authenticated heartbeats and timeout-based device status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.repositories.device_repository import DeviceRepository


OPERATOR_TOKEN = "device-operator-token"
JETSON_TOKEN = "device-jetson-token"
OPERATOR_HEADERS = {"X-Operator-Token": OPERATOR_TOKEN}
JETSON_HEADERS = {"X-Jetson-Token": JETSON_TOKEN}


@dataclass(frozen=True)
class DeviceTestContext:
    client: TestClient
    devices: DeviceRepository


@pytest.fixture
def device_api(tmp_path: Path) -> DeviceTestContext:
    database_path = tmp_path / "devices.db"
    settings = Settings(
        app_name="Device API Test",
        environment="test",
        cors_origins=("http://localhost:5173",),
        log_level="WARNING",
        database_path=database_path,
        operator_api_token=OPERATOR_TOKEN,
        jetson_api_token=JETSON_TOKEN,
        heartbeat_timeout_seconds=5.0,
    )
    with TestClient(create_app(settings)) as client:
        yield DeviceTestContext(client=client, devices=DeviceRepository(database_path))


def test_heartbeat_registers_device_with_backend_receipt_time(
    device_api: DeviceTestContext,
) -> None:
    old_device_time = "2020-01-02T03:04:05+00:00"
    before = datetime.now(timezone.utc)

    response = device_api.client.post(
        "/api/devices/jetson-sim/heartbeat",
        headers=JETSON_HEADERS,
        json={"device_timestamp": old_device_time},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "jetson-sim"
    assert body["status"] == "online"
    assert body["transport"] == "wifi"
    assert datetime.fromisoformat(body["last_seen_at"]) >= before
    assert body["last_seen_at"] != old_device_time
    assert device_api.client.get("/api/status").json()["jetson_status"] == "online"


def test_device_and_operator_credentials_are_separate(
    device_api: DeviceTestContext,
) -> None:
    missing_jetson = device_api.client.post(
        "/api/devices/jetson-sim/heartbeat",
        json={},
    )
    operator_as_jetson = device_api.client.post(
        "/api/devices/jetson-sim/heartbeat",
        headers={"X-Jetson-Token": OPERATOR_TOKEN},
        json={},
    )
    missing_operator = device_api.client.get("/api/devices")
    jetson_as_operator = device_api.client.get(
        "/api/devices",
        headers={"X-Operator-Token": JETSON_TOKEN},
    )

    assert missing_jetson.status_code == 401
    assert operator_as_jetson.status_code == 401
    assert missing_operator.status_code == 401
    assert jetson_as_operator.status_code == 401


def test_device_becomes_offline_after_heartbeat_timeout(
    device_api: DeviceTestContext,
) -> None:
    device_api.client.post(
        "/api/devices/jetson-sim/heartbeat",
        headers=JETSON_HEADERS,
        json={},
    )
    timed_out_at = datetime.now(timezone.utc) - timedelta(seconds=6)
    device_api.devices.update_status(
        "jetson-sim",
        status="online",
        last_seen_at=timed_out_at,
    )

    response = device_api.client.get("/api/devices", headers=OPERATOR_HEADERS)

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["items"][0]["status"] == "offline"
    assert device_api.devices.get("jetson-sim").status == "offline"
    assert device_api.client.get("/api/status").json()["jetson_status"] == "offline"


def test_recent_heartbeat_keeps_device_online(device_api: DeviceTestContext) -> None:
    device_api.client.post(
        "/api/devices/jetson-sim/heartbeat",
        headers=JETSON_HEADERS,
        json={},
    )

    response = device_api.client.get("/api/devices", headers=OPERATOR_HEADERS)

    assert response.json()["items"][0]["status"] == "online"
    assert response.json()["items"][0]["heartbeat_timeout_seconds"] == 5.0


def test_invalid_device_id_and_naive_device_time_are_rejected(
    device_api: DeviceTestContext,
) -> None:
    invalid_id = device_api.client.post(
        "/api/devices/bad%20id/heartbeat",
        headers=JETSON_HEADERS,
        json={},
    )
    naive_time = device_api.client.post(
        "/api/devices/jetson-sim/heartbeat",
        headers=JETSON_HEADERS,
        json={"device_timestamp": "2026-01-02T03:04:05"},
    )

    assert invalid_id.status_code == 422
    assert naive_time.status_code == 422
