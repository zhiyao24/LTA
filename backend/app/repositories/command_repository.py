"""SQLite persistence and atomic queue operations for simulated commands."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from ..constants.commands import (
    DEFAULT_COMMAND_EXPIRY_SECONDS,
    NORMAL_PRIORITY,
    STOP_PRIORITY,
    CommandStatus,
    CommandType,
)
from ..database import (
    DatabasePath,
    decode_json,
    from_utc_text,
    open_connection,
    to_utc_text,
    utc_now,
    validate_json,
)
from ..models import Command, CommandStatusEvent


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS commands (
        id TEXT PRIMARY KEY,
        device_id TEXT NOT NULL,
        command_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT,
        acknowledged_at TEXT,
        result_json TEXT,
        FOREIGN KEY (device_id) REFERENCES devices (id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS command_status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        command_id TEXT NOT NULL,
        status TEXT NOT NULL,
        changed_at TEXT NOT NULL,
        details_json TEXT,
        FOREIGN KEY (command_id) REFERENCES commands (id)
            ON UPDATE CASCADE ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_commands_device_created
    ON commands (device_id, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_commands_queue
    ON commands (device_id, status, expires_at, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_commands_status_expires
    ON commands (status, expires_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_command_history_command_changed
    ON command_status_history (command_id, changed_at, id)
    """,
)


class InvalidStatusTransitionError(ValueError):
    """Raised when a command cannot move from its current state to a target state."""


class DuplicateStatusEventError(ValueError):
    """Raised when one acknowledgement ID is reused for a different event."""


def _required_timestamp(row: sqlite3.Row, column: str) -> datetime:
    value = from_utc_text(row[column])
    if value is None:
        raise ValueError(f"Command {column} is missing")
    return value


def _command_from_row(row: sqlite3.Row) -> Command:
    return Command(
        id=row["id"],
        device_id=row["device_id"],
        command_type=row["command_type"],
        payload=decode_json(row["payload_json"]),
        status=row["status"],
        created_at=_required_timestamp(row, "created_at"),
        expires_at=from_utc_text(row["expires_at"]),
        acknowledged_at=from_utc_text(row["acknowledged_at"]),
        result=decode_json(row["result_json"]),
    )


def _status_event_from_row(row: sqlite3.Row) -> CommandStatusEvent:
    changed_at = from_utc_text(row["changed_at"])
    if changed_at is None:
        raise ValueError("Command history changed_at is missing")
    return CommandStatusEvent(
        id=row["id"],
        event_id=row["event_id"],
        command_id=row["command_id"],
        status=row["status"],
        changed_at=changed_at,
        details=decode_json(row["details_json"]),
    )


def _insert_status_event(
    connection: sqlite3.Connection,
    *,
    command_id: str,
    status: str,
    changed_at: datetime,
    event_id: str | None = None,
    details: Any | None = None,
) -> None:
    details_json = (
        validate_json(details, field_name="status history details")
        if details is not None
        else None
    )
    connection.execute(
        """
        INSERT INTO command_status_history (
            event_id, command_id, status, changed_at, details_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            event_id or str(uuid4()),
            command_id,
            status,
            to_utc_text(changed_at, field_name="changed_at"),
            details_json,
        ),
    )


def _expire_stale_rows(connection: sqlite3.Connection, *, now: datetime) -> int:
    now_text = to_utc_text(now, field_name="now")
    rows = connection.execute(
        """
        SELECT id FROM commands
        WHERE status IN (?, ?)
          AND (expires_at IS NULL OR expires_at <= ?)
        """,
        (
            CommandStatus.PENDING.value,
            CommandStatus.DELIVERED.value,
            now_text,
        ),
    ).fetchall()

    expired_count = 0
    for row in rows:
        cursor = connection.execute(
            """
            UPDATE commands
            SET status = ?
            WHERE id = ? AND status IN (?, ?)
            """,
            (
                CommandStatus.EXPIRED.value,
                row["id"],
                CommandStatus.PENDING.value,
                CommandStatus.DELIVERED.value,
            ),
        )
        if cursor.rowcount:
            _insert_status_event(
                connection,
                command_id=row["id"],
                status=CommandStatus.EXPIRED.value,
                changed_at=now,
                details={"reason": "expiry_time_reached"},
            )
            expired_count += 1
    return expired_count


class CommandRepository:
    """Store commands and make each queue transition in one transaction."""

    def __init__(self, database_path: DatabasePath) -> None:
        self.database_path = database_path

    def create(
        self,
        *,
        device_id: str,
        command_type: str,
        payload: Any,
        status: str = CommandStatus.PENDING.value,
        expires_at: datetime | None = None,
        created_at: datetime | None = None,
        command_id: str | None = None,
    ) -> Command:
        identifier = command_id or str(uuid4())
        normalized_type = CommandType(command_type).value
        normalized_status = CommandStatus(status).value
        created = created_at or utc_now()
        expires = expires_at or created + timedelta(seconds=DEFAULT_COMMAND_EXPIRY_SECONDS)
        if expires <= created:
            raise ValueError("expires_at must be later than created_at")
        payload_json = validate_json(payload, field_name="payload")

        with open_connection(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO commands (
                    id, device_id, command_type, payload_json, status,
                    created_at, expires_at, acknowledged_at, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    identifier,
                    device_id,
                    normalized_type,
                    payload_json,
                    normalized_status,
                    to_utc_text(created, field_name="created_at"),
                    to_utc_text(expires, field_name="expires_at"),
                ),
            )
            _insert_status_event(
                connection,
                command_id=identifier,
                status=normalized_status,
                changed_at=created,
            )
            row = connection.execute(
                "SELECT * FROM commands WHERE id = ?",
                (identifier,),
            ).fetchone()

        if row is None:
            raise RuntimeError("The command insert did not return a record")
        return _command_from_row(row)

    def get(self, command_id: str) -> Command | None:
        with open_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM commands WHERE id = ?",
                (command_id,),
            ).fetchone()
        return _command_from_row(row) if row else None

    def list(
        self,
        *,
        device_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Command]:
        conditions: list[str] = []
        parameters: list[str | int] = []
        if device_id is not None:
            conditions.append("device_id = ?")
            parameters.append(device_id)
        if status is not None:
            normalized_status = CommandStatus(status).value
            conditions.append("status = ?")
            parameters.append(normalized_status)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(min(max(1, limit), 500))
        with open_connection(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM commands
                {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,  # The interpolated clause contains only fixed strings above.
                tuple(parameters),
            ).fetchall()
        return [_command_from_row(row) for row in rows]

    def list_for_device(self, device_id: str, *, limit: int = 100) -> list[Command]:
        return self.list(device_id=device_id, limit=limit)

    def status_history(self, command_id: str) -> list[CommandStatusEvent]:
        with open_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM command_status_history
                WHERE command_id = ?
                ORDER BY changed_at, id
                """,
                (command_id,),
            ).fetchall()
        return [_status_event_from_row(row) for row in rows]

    def update_status(
        self,
        command_id: str,
        *,
        status: str,
        acknowledged_at: datetime | None = None,
        result: Any | None = None,
    ) -> Command | None:
        """Update a status and audit it; API workflows use transition_status."""

        normalized_status = CommandStatus(status).value
        changed_at = acknowledged_at or utc_now()
        result_json = (
            validate_json(result, field_name="result") if result is not None else None
        )
        with open_connection(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE commands
                SET status = ?, acknowledged_at = ?, result_json = ?
                WHERE id = ?
                """,
                (
                    normalized_status,
                    to_utc_text(acknowledged_at, field_name="acknowledged_at")
                    if acknowledged_at
                    else None,
                    result_json,
                    command_id,
                ),
            )
            if cursor.rowcount:
                _insert_status_event(
                    connection,
                    command_id=command_id,
                    status=normalized_status,
                    changed_at=changed_at,
                    details=result,
                )
            row = connection.execute(
                "SELECT * FROM commands WHERE id = ?",
                (command_id,),
            ).fetchone()
        return _command_from_row(row) if row else None

    def expire_stale(self, *, now: datetime | None = None) -> int:
        checked_at = now or utc_now()
        with open_connection(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            return _expire_stale_rows(connection, now=checked_at)

    def claim_next_for_device(
        self,
        device_id: str,
        *,
        now: datetime | None = None,
    ) -> Command | None:
        """Atomically expire stale work and mark one pending command delivered."""

        claimed_at = now or utc_now()
        claimed_at_text = to_utc_text(claimed_at, field_name="claimed_at")
        with open_connection(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            _expire_stale_rows(connection, now=claimed_at)
            candidate = connection.execute(
                """
                SELECT id FROM commands
                WHERE device_id = ?
                  AND status = ?
                  AND expires_at > ?
                ORDER BY
                    CASE WHEN command_type = ? THEN ? ELSE ? END,
                    created_at,
                    id
                LIMIT 1
                """,
                (
                    device_id,
                    CommandStatus.PENDING.value,
                    claimed_at_text,
                    CommandType.STOP.value,
                    STOP_PRIORITY,
                    NORMAL_PRIORITY,
                ),
            ).fetchone()
            if candidate is None:
                return None

            cursor = connection.execute(
                """
                UPDATE commands SET status = ?
                WHERE id = ? AND status = ?
                """,
                (
                    CommandStatus.DELIVERED.value,
                    candidate["id"],
                    CommandStatus.PENDING.value,
                ),
            )
            if cursor.rowcount != 1:
                return None
            _insert_status_event(
                connection,
                command_id=candidate["id"],
                status=CommandStatus.DELIVERED.value,
                changed_at=claimed_at,
                details={"delivery": "simulated_poll"},
            )
            row = connection.execute(
                "SELECT * FROM commands WHERE id = ?",
                (candidate["id"],),
            ).fetchone()
        return _command_from_row(row) if row else None

    def transition_status(
        self,
        command_id: str,
        *,
        expected_statuses: tuple[str, ...],
        status: str,
        event_id: str,
        changed_at: datetime | None = None,
        result: Any | None = None,
    ) -> Command | None:
        """Apply one authenticated Jetson status event exactly once."""

        target_status = CommandStatus(status).value
        allowed_from = tuple(CommandStatus(item).value for item in expected_statuses)
        event_time = changed_at or utc_now()
        result_json = (
            validate_json(result, field_name="result") if result is not None else None
        )

        with open_connection(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior_event = connection.execute(
                "SELECT * FROM command_status_history WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if prior_event is not None:
                if (
                    prior_event["command_id"] != command_id
                    or prior_event["status"] != target_status
                ):
                    raise DuplicateStatusEventError(
                        "The acknowledgement ID was already used for another status change"
                    )
                current = connection.execute(
                    "SELECT * FROM commands WHERE id = ?",
                    (command_id,),
                ).fetchone()
                return _command_from_row(current) if current else None

            row = connection.execute(
                "SELECT * FROM commands WHERE id = ?",
                (command_id,),
            ).fetchone()
            if row is None:
                return None

            current_status = row["status"]
            if current_status not in allowed_from:
                raise InvalidStatusTransitionError(
                    f"Cannot change command from {current_status} to {target_status}"
                )

            connection.execute(
                """
                UPDATE commands
                SET status = ?, acknowledged_at = ?, result_json = ?
                WHERE id = ?
                """,
                (
                    target_status,
                    to_utc_text(event_time, field_name="acknowledged_at"),
                    result_json,
                    command_id,
                ),
            )
            _insert_status_event(
                connection,
                command_id=command_id,
                status=target_status,
                changed_at=event_time,
                event_id=event_id,
                details=result,
            )
            updated = connection.execute(
                "SELECT * FROM commands WHERE id = ?",
                (command_id,),
            ).fetchone()
        return _command_from_row(updated) if updated else None
