"""SQLite queries for snapshots received from an external API."""

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
from ..models import ExternalApiSnapshot


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS external_api_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        received_at TEXT NOT NULL,
        data_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_external_snapshots_source_received
    ON external_api_snapshots (source, received_at DESC)
    """,
)


def _snapshot_from_row(row: sqlite3.Row) -> ExternalApiSnapshot:
    received_at = from_utc_text(row["received_at"])
    if received_at is None:
        raise ValueError("External snapshot received_at is missing")
    return ExternalApiSnapshot(
        id=row["id"],
        source=row["source"],
        received_at=received_at,
        data=decode_json(row["data_json"]),
    )


class ExternalDataRepository:
    """Insert and read immutable external API snapshots."""

    def __init__(self, database_path: DatabasePath) -> None:
        self.database_path = database_path

    def create(
        self,
        *,
        source: str,
        data: Any,
        received_at: datetime | None = None,
    ) -> ExternalApiSnapshot:
        received = received_at or utc_now()
        data_json = validate_json(data, field_name="data")

        with open_connection(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO external_api_snapshots (source, received_at, data_json)
                VALUES (?, ?, ?)
                """,
                (
                    source,
                    to_utc_text(received, field_name="received_at"),
                    data_json,
                ),
            )
            row = connection.execute(
                "SELECT * FROM external_api_snapshots WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()

        if row is None:
            raise RuntimeError("The external snapshot insert did not return a record")
        return _snapshot_from_row(row)

    def latest(self, *, source: str | None = None) -> ExternalApiSnapshot | None:
        with open_connection(self.database_path) as connection:
            if source is None:
                row = connection.execute(
                    """
                    SELECT * FROM external_api_snapshots
                    ORDER BY received_at DESC, id DESC
                    LIMIT 1
                    """
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT * FROM external_api_snapshots
                    WHERE source = ?
                    ORDER BY received_at DESC, id DESC
                    LIMIT 1
                    """,
                    (source,),
                ).fetchone()
        return _snapshot_from_row(row) if row else None

    def prune_bus_arrivals(self, *, keep: int) -> None:
        """Bound automatic bus history without touching other external snapshots."""
        if keep < 1:
            raise ValueError("keep must be positive")
        with open_connection(self.database_path) as connection:
            connection.execute(
                """
                DELETE FROM external_api_snapshots
                WHERE id IN (
                    SELECT id FROM external_api_snapshots
                    WHERE source LIKE 'lta-bus-arrival:%'
                    ORDER BY received_at DESC, id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (keep,),
            )
