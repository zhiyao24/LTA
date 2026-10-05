"""Tests for strict telemetry ingestion, freshness, history, and retention."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.repositories.device_repository import DeviceRepository
from backend.app.repositories.telemetry_repository import TelemetryRepository


OPERATOR_TOKEN = "telemetry-operator-token"
JETSON_TOKEN = "telemetry-jetson-token"
OPERATOR_HEADERS = {"X-Operator-Token": OPERATOR_TOKEN}
JETSON_HEADERS = {"X-Jetson-Token": JETSON_TOKEN}


@dataclass(frozen=True)
class TelemetryTestContext:
    client: TestClient
    devices: DeviceRepository
    telemetry: TelemetryRepository


@pytest.fixture
def telemetry_api(tmp_path: Path) -> TelemetryTestContext:
    database_path = tmp_path / "telemetry.db"
    settings = Settings(
        app_name="Telemetry API Test",
        environment="test",
        cors_origins=("http://localhost:5173",),
        log_level="WARNING",
        database_path=database_path,
        operator_api_token=OPERATOR_TOKEN,
        jetson_api_token=JETSON_TOKEN,
        heartbeat_timeout_seconds=5.0,
        telemetry_stale_after_seconds=10.0,
        telemetry_retention_hours=1.0,
    )
    with TestClient(create_app(settings)) as client:
        yield TelemetryTestContext(
            client=client,
            devices=DeviceRepository(database_path),
            telemetry=TelemetryRepository(database_path),
        )


def _payload(**readings: float) -> dict[str, object]:
    return {
        "device_timestamp": datetime.now(timezone.utc).isoformat(),
        "data": readings or {"cpu_temperature_c": 44.5},
    }


def test_telemetry_is_authenticated_validated_and_timestamped_separately(
    telemetry_api: TelemetryTestContext,
) -> None:
    device_time = datetime.now(timezone.utc) - timedelta(minutes=2)
    before = datetime.now(timezone.utc)
    payload = {
        "device_timestamp": device_time.isoformat(),
        "data": {
            "cpu_temperature_c": 45.2,
            "supply_voltage_v": 5.02,
        },
    }

    unauthorized = telemetry_api.client.post(
        "/api/devices/jetson-sim/telemetry",
        json=payload,
    )
    response = telemetry_api.client.post(
        "/api/devices/jetson-sim/telemetry",
        headers=JETSON_HEADERS,
        json=payload,
    )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    body = response.json()
    assert datetime.fromisoformat(body["received_at"]) >= before
    assert datetime.fromisoformat(body["device_timestamp"]) == device_time
    assert body["data"] == {
        "cpu_temperature_c": 45.2,
        "supply_voltage_v": 5.02,
    }
    assert body["is_stale"] is False
    assert telemetry_api.devices.get("jetson-sim").status == "online"


@pytest.mark.parametrize(
    "payload",
    [
        {"device_timestamp": "2026-01-02T03:04:05+00:00", "data": {}},
        _payload(cpu_temperature_c=126.0),
        _payload(memory_used_percent=-0.1),
        _payload(supply_voltage_v=True),
        _payload(unknown_reading=12.0),
        {"device_timestamp": "2026-01-02T03:04:05", "data": {"cpu_temperature_c": 40}},
    ],
)
def test_invalid_telemetry_is_rejected(
    telemetry_api: TelemetryTestContext,
    payload: dict[str, object],
) -> None:
    response = telemetry_api.client.post(
        "/api/devices/jetson-sim/telemetry",
        headers=JETSON_HEADERS,
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_latest_telemetry_is_marked_stale_from_backend_receipt_time(
    telemetry_api: TelemetryTestContext,
) -> None:
    now = datetime.now(timezone.utc)
    telemetry_api.devices.record_heartbeat("jetson-sim", received_at=now)
    telemetry_api.telemetry.create(
        device_id="jetson-sim",
        received_at=now - timedelta(seconds=11),
        device_timestamp=now - timedelta(seconds=12),
        data={"wifi_signal_dbm": -55.0},
    )

    response = telemetry_api.client.get(
        "/api/devices/jetson-sim/telemetry/latest",
        headers=OPERATOR_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["is_stale"] is True
    assert response.json()["data"] == {"wifi_signal_dbm": -55.0}


def test_history_is_newest_first_and_query_size_is_limited(
    telemetry_api: TelemetryTestContext,
) -> None:
    now = datetime.now(timezone.utc)
    telemetry_api.devices.record_heartbeat("jetson-sim", received_at=now)
    for offset in range(3):
        telemetry_api.telemetry.create(
            device_id="jetson-sim",
            received_at=now + timedelta(seconds=offset),
            device_timestamp=now + timedelta(seconds=offset),
            data={"memory_used_percent": 30.0 + offset},
        )

    response = telemetry_api.client.get(
        "/api/devices/jetson-sim/telemetry/history?limit=2",
        headers=OPERATOR_HEADERS,
    )
    too_large = telemetry_api.client.get(
        "/api/devices/jetson-sim/telemetry/history?limit=501",
        headers=OPERATOR_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert response.json()["limit"] == 2
    assert [item["data"]["memory_used_percent"] for item in response.json()["items"]] == [
        32.0,
        31.0,
    ]
    assert too_large.status_code == 422


def test_new_telemetry_prunes_rows_outside_retention(
    telemetry_api: TelemetryTestContext,
) -> None:
    now = datetime.now(timezone.utc)
    telemetry_api.devices.record_heartbeat("jetson-sim", received_at=now)
    telemetry_api.telemetry.create(
        device_id="jetson-sim",
        received_at=now - timedelta(hours=2),
        device_timestamp=now - timedelta(hours=2),
        data={"cpu_temperature_c": 40.0},
    )

    response = telemetry_api.client.post(
        "/api/devices/jetson-sim/telemetry",
        headers=JETSON_HEADERS,
        json=_payload(cpu_temperature_c=45.0),
    )
    history = telemetry_api.client.get(
        "/api/devices/jetson-sim/telemetry/history",
        headers=OPERATOR_HEADERS,
    )

    assert response.status_code == 200
    assert history.json()["count"] == 1
    assert history.json()["items"][0]["data"] == {"cpu_temperature_c": 45.0}


def test_missing_device_and_missing_telemetry_return_clear_errors(
    telemetry_api: TelemetryTestContext,
) -> None:
    missing_device = telemetry_api.client.get(
        "/api/devices/missing/telemetry/latest",
        headers=OPERATOR_HEADERS,
    )
    telemetry_api.devices.record_heartbeat("jetson-empty")
    missing_telemetry = telemetry_api.client.get(
        "/api/devices/jetson-empty/telemetry/latest",
        headers=OPERATOR_HEADERS,
    )

    assert missing_device.status_code == 404
    assert missing_device.json()["error"]["code"] == "device_not_found"
    assert missing_telemetry.status_code == 404
    assert missing_telemetry.json()["error"]["code"] == "telemetry_not_found"

