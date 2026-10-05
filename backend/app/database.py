"""Small SQLite helpers shared by the persistence repositories."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DatabasePath = str | Path


def utc_now() -> datetime:
    """Return a timezone-aware timestamp in UTC."""

    return datetime.now(timezone.utc)


def to_utc_text(value: datetime, *, field_name: str) -> str:
    """Validate and serialize a timezone-aware datetime for SQLite."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def from_utc_text(value: str | None) -> datetime | None:
    """Turn a stored ISO 8601 timestamp back into a UTC datetime."""

    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Stored timestamp does not include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_json(value: Any, *, field_name: str) -> str:
    """Validate JSON input and return one consistent serialized representation.

    Strings are treated as already-serialized JSON. Other Python values are
    serialized directly. NaN and infinity are rejected because they are not
    valid JSON values.
    """

    try:
        decoded = json.loads(value) if isinstance(value, str) else value
        return json.dumps(
            decoded,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exception:
        raise ValueError(f"{field_name} must contain valid JSON") from exception


def decode_json(value: str | None) -> Any:
    """Deserialize a required or optional JSON database value."""

    return None if value is None else json.loads(value)


@contextmanager
def open_connection(database_path: DatabasePath) -> Iterator[sqlite3.Connection]:
    """Open one SQLite connection for one repository operation."""

    path_text = str(database_path)
    if path_text != ":memory:":
        Path(path_text).parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path_text, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: DatabasePath) -> None:
    """Create any missing tables and indexes without removing existing data."""

    # Imports stay here to avoid a module cycle: repositories use the connection
    # helper above, while this function collects their schema statements.
    from .repositories.command_repository import SCHEMA_STATEMENTS as command_schema
    from .repositories.device_repository import SCHEMA_STATEMENTS as device_schema
    from .repositories.external_data_repository import (
        SCHEMA_STATEMENTS as external_data_schema,
    )
    from .repositories.telemetry_repository import SCHEMA_STATEMENTS as telemetry_schema

    with open_connection(database_path) as connection:
        for statement in (
            *device_schema,
            *command_schema,
            *telemetry_schema,
            *external_data_schema,
        ):
            connection.execute(statement)
