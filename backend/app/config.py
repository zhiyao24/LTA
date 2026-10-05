"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from secrets import compare_digest
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)
BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
DEFAULT_DATABASE_PATH = BACKEND_ROOT / "data" / "lta.db"
LTA_BUS_ARRIVAL_URL = "https://datamall2.mytransport.sg/ltaodataservice/v3/BusArrival"


@dataclass(frozen=True)
class Settings:
    """Configuration values used by the FastAPI application."""

    app_name: str
    environment: str
    cors_origins: tuple[str, ...]
    log_level: str
    database_path: Path
    external_api_mode: str = "mock"
    external_api_url: str | None = None
    external_api_key: str | None = field(default=None, repr=False)
    external_api_timeout_seconds: float = 5.0
    operator_api_token: str | None = field(default=None, repr=False)
    jetson_api_token: str | None = field(default=None, repr=False)
    heartbeat_timeout_seconds: float = 10.0
    telemetry_stale_after_seconds: float = 15.0
    telemetry_retention_hours: float = 168.0
    lta_api_account_key: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Prevent one credential from crossing the operator/device boundary."""

        if (
            self.operator_api_token
            and self.jetson_api_token
            and compare_digest(self.operator_api_token, self.jetson_api_token)
        ):
            raise ValueError("OPERATOR_API_TOKEN and JETSON_API_TOKEN must be different.")


def _parse_database_path(raw_value: str | None) -> Path:
    """Resolve an optional database path without hardcoding a user's home folder."""

    if not raw_value:
        return DEFAULT_DATABASE_PATH

    configured_path = Path(raw_value).expanduser()
    if configured_path.is_absolute() or configured_path == Path(":memory:"):
        return configured_path
    return PROJECT_ROOT / configured_path


def _parse_cors_origins(raw_value: str | None) -> tuple[str, ...]:
    """Convert a comma-separated environment value into validated origins."""

    if not raw_value:
        return DEFAULT_CORS_ORIGINS

    origins = tuple(
        dict.fromkeys(origin.strip().rstrip("/") for origin in raw_value.split(",") if origin.strip())
    )

    if not origins:
        return DEFAULT_CORS_ORIGINS

    for origin in origins:
        parsed = urlparse(origin)
        if origin == "*" or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                "CORS_ORIGINS must contain explicit http:// or https:// origins; wildcards are not allowed."
            )

    return origins


def _parse_external_api_mode(raw_value: str | None) -> str:
    """Accept mock mode now and an explicit HTTP mode for later integration."""

    mode = (raw_value or "mock").strip().lower()
    if mode not in {"mock", "http"}:
        raise ValueError("EXTERNAL_API_MODE must be either 'mock' or 'http'.")
    return mode


def _parse_external_api_timeout(raw_value: str | None) -> float:
    """Read a bounded timeout so a bad configuration cannot hang requests."""

    try:
        timeout = float(raw_value or "5")
    except ValueError as exception:
        raise ValueError("EXTERNAL_API_TIMEOUT_SECONDS must be a number.") from exception

    if not 0 < timeout <= 60:
        raise ValueError("EXTERNAL_API_TIMEOUT_SECONDS must be greater than 0 and at most 60.")
    return timeout


def _parse_bounded_float(
    raw_value: str | None,
    *,
    default: float,
    minimum: float,
    maximum: float,
    variable_name: str,
) -> float:
    """Read one positive, bounded duration from the environment."""

    try:
        value = float(raw_value) if raw_value is not None else default
    except ValueError as exception:
        raise ValueError(f"{variable_name} must be a number.") from exception
    if not minimum <= value <= maximum:
        raise ValueError(
            f"{variable_name} must be between {minimum:g} and {maximum:g}."
        )
    return value


def _optional_secret(raw_value: str | None) -> str | None:
    """Treat blank token settings as disabled without exposing their values."""

    value = raw_value.strip() if raw_value else ""
    return value or None


@lru_cache
def get_settings() -> Settings:
    """Read settings once from the current process environment."""

    return Settings(
        app_name=os.environ.get("APP_NAME", "Local Jetson Control API"),
        environment=os.environ.get("APP_ENV", "development"),
        cors_origins=_parse_cors_origins(os.environ.get("CORS_ORIGINS")),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        database_path=_parse_database_path(os.environ.get("DATABASE_PATH")),
        external_api_mode=_parse_external_api_mode(os.environ.get("EXTERNAL_API_MODE")),
        external_api_url=os.environ.get("EXTERNAL_API_URL") or None,
        external_api_key=os.environ.get("EXTERNAL_API_KEY") or None,
        lta_api_account_key=_optional_secret(os.environ.get("LTA_API_ACCOUNT_KEY")),
        external_api_timeout_seconds=_parse_external_api_timeout(
            os.environ.get("EXTERNAL_API_TIMEOUT_SECONDS")
        ),
        operator_api_token=_optional_secret(os.environ.get("OPERATOR_API_TOKEN")),
        jetson_api_token=_optional_secret(os.environ.get("JETSON_API_TOKEN")),
        heartbeat_timeout_seconds=_parse_bounded_float(
            os.environ.get("JETSON_HEARTBEAT_TIMEOUT_SECONDS"),
            default=10.0,
            minimum=1.0,
            maximum=3600.0,
            variable_name="JETSON_HEARTBEAT_TIMEOUT_SECONDS",
        ),
        telemetry_stale_after_seconds=_parse_bounded_float(
            os.environ.get("TELEMETRY_STALE_AFTER_SECONDS"),
            default=15.0,
            minimum=1.0,
            maximum=86400.0,
            variable_name="TELEMETRY_STALE_AFTER_SECONDS",
        ),
        telemetry_retention_hours=_parse_bounded_float(
            os.environ.get("TELEMETRY_RETENTION_HOURS"),
            default=168.0,
            minimum=1.0,
            maximum=8760.0,
            variable_name="TELEMETRY_RETENTION_HOURS",
        ),
    )
