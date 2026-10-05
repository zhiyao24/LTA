"""SQLite queries for registered Jetson devices."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ..database import DatabasePath, from_utc_text, open_connection, to_utc_text, utc_now
from ..models import Device


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS devices (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        transport TEXT NOT NULL,
        status TEXT NOT NULL,
        last_seen_at TEXT,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_devices_status ON devices (status)",
    "CREATE INDEX IF NOT EXISTS idx_devices_last_seen_at ON devices (last_seen_at)",
)


def _device_from_row(row: sqlite3.Row) -> Device:
    created_at = from_utc_text(row["created_at"])
    if created_at is None:  # The schema prevents this; this guard helps type checking.
        raise ValueError("Device created_at is missing")
    return Device(
        id=row["id"],
        name=row["name"],
        transport=row["transport"],
        status=row["status"],
        last_seen_at=from_utc_text(row["last_seen_at"]),
        created_at=created_at,
    )


class DeviceRepository:
    """Create and read device records using short-lived connections."""

    def __init__(self, database_path: DatabasePath) -> None:
        self.database_path = database_path

    def create(
        self,
        *,
        device_id: str,
        name: str,
        transport: str,
        status: str = "offline",
        last_seen_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> Device:
        created = created_at or utc_now()
        with open_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO devices (id, name, transport, status, last_seen_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    name,
                    transport,
                    status,
                    to_utc_text(last_seen_at, field_name="last_seen_at")
                    if last_seen_at
                    else None,
                    to_utc_text(created, field_name="created_at"),
                ),
            )
            row = connection.execute(
                "SELECT * FROM devices WHERE id = ?",
                (device_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("The device insert did not return a record")
        return _device_from_row(row)

    def record_heartbeat(
        self,
        device_id: str,
        *,
        received_at: datetime | None = None,
    ) -> Device:
        """Atomically register or refresh one Wi-Fi device heartbeat."""

        seen_at = received_at or utc_now()
        seen_text = to_utc_text(seen_at, field_name="received_at")
        with open_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO devices (id, name, transport, status, last_seen_at, created_at)
                VALUES (?, ?, 'wifi', 'online', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    transport = 'wifi',
                    status = 'online',
                    last_seen_at = excluded.last_seen_at
                """,
                (device_id, device_id, seen_text, seen_text),
            )
            row = connection.execute(
                "SELECT * FROM devices WHERE id = ?",
                (device_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("The heartbeat update did not return a device")
        return _device_from_row(row)

    def get(self, device_id: str) -> Device | None:
        with open_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM devices WHERE id = ?",
                (device_id,),
            ).fetchone()
        return _device_from_row(row) if row else None

    def list(self, *, status: str | None = None) -> list[Device]:
        with open_connection(self.database_path) as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT * FROM devices ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM devices WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
        return [_device_from_row(row) for row in rows]

    def update_status(
        self,
        device_id: str,
        *,
        status: str,
        last_seen_at: datetime | None = None,
    ) -> Device | None:
        with open_connection(self.database_path) as connection:
            connection.execute(
                "UPDATE devices SET status = ?, last_seen_at = ? WHERE id = ?",
                (
                    status,
                    to_utc_text(last_seen_at, field_name="last_seen_at")
                    if last_seen_at
                    else None,
                    device_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM devices WHERE id = ?",
                (device_id,),
            ).fetchone()
        return _device_from_row(row) if row else None
