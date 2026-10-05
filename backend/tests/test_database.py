"""Tests for local SQLite initialization and repository operations."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.database import initialize_database, open_connection
from backend.app.repositories.command_repository import CommandRepository
from backend.app.repositories.device_repository import DeviceRepository
from backend.app.repositories.external_data_repository import ExternalDataRepository
from backend.app.repositories.telemetry_repository import TelemetryRepository


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "data" / "test-lta.db"
    initialize_database(path)
    return path


def test_initialization_is_repeatable_and_preserves_existing_rows(
    database_path: Path,
) -> None:
    devices = DeviceRepository(database_path)
    devices.create(
        device_id="jetson-primary",
        name="Bench Jetson",
        transport="wifi",
    )

    initialize_database(database_path)

    with open_connection(database_path) as connection:
        foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        table_rows = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        index_rows = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'index' AND name LIKE 'idx_%'
            """
        ).fetchall()

    assert database_path.exists()
    assert foreign_keys_enabled == 1
    assert {row["name"] for row in table_rows} == {
        "devices",
        "commands",
        "command_status_history",
        "telemetry",
        "external_api_snapshots",
    }
    assert len(index_rows) >= 6
    assert devices.get("jetson-primary") is not None


def test_device_insert_query_and_status_update(database_path: Path) -> None:
    repository = DeviceRepository(database_path)
    created_at = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
    seen_at = datetime(2026, 1, 2, 3, 5, tzinfo=timezone.utc)

    created = repository.create(
        device_id="jetson-1",
        name="Jetson Nano",
        transport="wifi",
        created_at=created_at,
    )
    updated = repository.update_status(
        "jetson-1",
        status="online",
        last_seen_at=seen_at,
    )

    assert created.status == "offline"
    assert created.created_at == created_at
    assert repository.get("jetson-1") == updated
    assert updated is not None
    assert updated.status == "online"
    assert updated.last_seen_at == seen_at
    assert repository.list(status="online") == [updated]


def test_command_insert_query_and_acknowledgement_update(database_path: Path) -> None:
    DeviceRepository(database_path).create(
        device_id="jetson-1",
        name="Jetson Nano",
        transport="wifi",
    )
    repository = CommandRepository(database_path)
    created_at = datetime(2026, 2, 3, 4, 5, tzinfo=timezone.utc)
    acknowledged_at = created_at + timedelta(seconds=2)

    created = repository.create(
        command_id="command-1",
        device_id="jetson-1",
        command_type="SET_MODE",
        payload={"mode": "manual"},
        created_at=created_at,
        expires_at=created_at + timedelta(seconds=30),
    )
    updated = repository.update_status(
        "command-1",
        status="completed",
        acknowledged_at=acknowledged_at,
        result={"accepted": True},
    )

    assert created.payload == {"mode": "manual"}
    assert updated is not None
    assert updated.status == "completed"
    assert updated.acknowledged_at == acknowledged_at
    assert updated.result == {"accepted": True}
    assert repository.get("command-1") == updated
    assert repository.list_for_device("jetson-1") == [updated]
    assert [event.status for event in repository.status_history("command-1")] == [
        "pending",
        "completed",
    ]


def test_telemetry_and_external_snapshot_inserts_and_queries(
    database_path: Path,
) -> None:
    DeviceRepository(database_path).create(
        device_id="jetson-1",
        name="Jetson Nano",
        transport="wifi",
    )
    telemetry = TelemetryRepository(database_path)
    external_data = ExternalDataRepository(database_path)
    first_time = datetime(2026, 3, 4, 5, 6, tzinfo=timezone.utc)
    second_time = first_time + timedelta(seconds=1)

    first = telemetry.create(
        device_id="jetson-1",
        data={"temperature_c": 41.5},
        received_at=first_time,
        device_timestamp=first_time - timedelta(milliseconds=50),
    )
    second = telemetry.create(
        device_id="jetson-1",
        data='{"temperature_c":42.0}',
        received_at=second_time,
    )
    snapshot = external_data.create(
        source="example-service",
        data={"value": 17, "valid": True},
        received_at=second_time,
    )

    assert first.data == {"temperature_c": 41.5}
    assert telemetry.latest_for_device("jetson-1") == [second, first]
    assert snapshot.data == {"valid": True, "value": 17}
    assert external_data.latest(source="example-service") == snapshot
    assert external_data.latest(source="missing") is None


def test_invalid_json_is_rejected_before_insert(database_path: Path) -> None:
    DeviceRepository(database_path).create(
        device_id="jetson-1",
        name="Jetson Nano",
        transport="wifi",
    )

    with pytest.raises(ValueError, match="payload must contain valid JSON"):
        CommandRepository(database_path).create(
            device_id="jetson-1",
            command_type="SET_SPEED",
            payload="{not valid json}",
        )

    with pytest.raises(ValueError, match="data must contain valid JSON"):
        ExternalDataRepository(database_path).create(
            source="example-service",
            data={"invalid_number": float("nan")},
        )


def test_invalid_device_foreign_keys_are_rejected(database_path: Path) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        CommandRepository(database_path).create(
            device_id="missing-device",
            command_type="STOP",
            payload={},
        )

    with pytest.raises(sqlite3.IntegrityError):
        TelemetryRepository(database_path).create(
            device_id="missing-device",
            data={"temperature_c": 40},
        )
