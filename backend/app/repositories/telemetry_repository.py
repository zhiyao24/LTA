"""SQLite queries for timestamped Jetson telemetry."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from ..database import (
    DatabasePath,
    decode_json,
    from_utc_text,
    open_connection,
    to_utc_text,
    utc_now,
    validate_json,
)
from ..models import Telemetry


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL,
        received_at TEXT NOT NULL,
        device_timestamp TEXT,
        data_json TEXT NOT NULL,
        FOREIGN KEY (device_id) REFERENCES devices (id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_telemetry_device_received
    ON telemetry (device_id, received_at DESC)
    """,
    "CREATE INDEX IF NOT EXISTS idx_telemetry_device_timestamp ON telemetry (device_timestamp)",
)


def _telemetry_from_row(row: sqlite3.Row) -> Telemetry:
    received_at = from_utc_text(row["received_at"])
    if received_at is None:
        raise ValueError("Telemetry received_at is missing")
    return Telemetry(
        id=row["id"],
        device_id=row["device_id"],
        received_at=received_at,
        device_timestamp=from_utc_text(row["device_timestamp"]),
        data=decode_json(row["data_json"]),
    )


class TelemetryRepository:
    """Insert telemetry and query the newest readings for one device."""

    def __init__(self, database_path: DatabasePath) -> None:
        self.database_path = database_path

    def create(
        self,
        *,
        device_id: str,
        data: Any,
        received_at: datetime | None = None,
        device_timestamp: datetime | None = None,
    ) -> Telemetry:
        received = received_at or utc_now()
        data_json = validate_json(data, field_name="data")

        with open_connection(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO telemetry (device_id, received_at, device_timestamp, data_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    device_id,
                    to_utc_text(received, field_name="received_at"),
                    to_utc_text(device_timestamp, field_name="device_timestamp")
                    if device_timestamp
                    else None,
                    data_json,
                ),
            )
            row = connection.execute(
                "SELECT * FROM telemetry WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()

        if row is None:
            raise RuntimeError("The telemetry insert did not return a record")
        return _telemetry_from_row(row)

    def latest_for_device(self, device_id: str, *, limit: int = 100) -> list[Telemetry]:
        with open_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM telemetry
                WHERE device_id = ?
                ORDER BY received_at DESC, id DESC
                LIMIT ?
                """,
                (device_id, max(1, limit)),
            ).fetchall()
        return [_telemetry_from_row(row) for row in rows]

    def latest(self, device_id: str) -> Telemetry | None:
        """Return one newest row without manufacturing missing readings."""

        readings = self.latest_for_device(device_id, limit=1)
        return readings[0] if readings else None

    def delete_older_than(self, cutoff: datetime) -> int:
        """Delete expired telemetry according to the configured retention window."""

        with open_connection(self.database_path) as connection:
            cursor = connection.execute(
                "DELETE FROM telemetry WHERE received_at < ?",
                (to_utc_text(cutoff, field_name="cutoff"),),
            )
        return cursor.rowcount
