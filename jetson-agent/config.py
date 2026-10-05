"""Environment-only configuration for the lightweight Jetson agent.

This module intentionally has no dependency on python-dotenv so it can run on
older Jetson Python installations with only the standard library.
"""

import os
from urllib.parse import urlsplit


class ConfigError(ValueError):
    """Raised when required agent configuration is missing or unsafe."""


class AgentConfig:
    def __init__(
        self,
        backend_url,
        device_id,
        device_token,
        poll_interval_seconds=2.0,
        request_timeout_seconds=5.0,
        dry_run=True,
    ):
        self.backend_url = backend_url
        self.device_id = device_id
        self.device_token = device_token
        self.poll_interval_seconds = poll_interval_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.dry_run = dry_run

    def __repr__(self):
        return (
            "AgentConfig(backend_url={0!r}, device_id={1!r}, device_token=<hidden>, "
            "poll_interval_seconds={2!r}, request_timeout_seconds={3!r}, "
            "dry_run={4!r})"
        ).format(
            self.backend_url,
            self.device_id,
            self.poll_interval_seconds,
            self.request_timeout_seconds,
            self.dry_run,
        )


def load_config() -> AgentConfig:
    """Load and validate settings without printing secret values."""

    backend_url = _required("BACKEND_URL").rstrip("/")
    parsed_url = urlsplit(backend_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ConfigError("BACKEND_URL must be a complete http:// or https:// URL.")

    device_id = _required("DEVICE_ID")
    if len(device_id) > 64 or not _valid_device_id(device_id):
        raise ConfigError(
            "DEVICE_ID must start with a letter or number and contain only letters, "
            "numbers, dots, underscores, or hyphens."
        )

    return AgentConfig(
        backend_url=backend_url,
        device_id=device_id,
        device_token=_required("DEVICE_TOKEN"),
        poll_interval_seconds=_bounded_float(
            "POLL_INTERVAL_SECONDS",
            default=2.0,
            minimum=0.1,
            maximum=60.0,
        ),
        request_timeout_seconds=_bounded_float(
            "REQUEST_TIMEOUT_SECONDS",
            default=5.0,
            minimum=0.1,
            maximum=30.0,
        ),
        dry_run=_boolean("DRY_RUN", default=True),
    )


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError("{0} is required.".format(name))
    return value


def _bounded_float(
    name: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    raw_value = os.environ.get(name)
    try:
        value = default if raw_value is None else float(raw_value)
    except ValueError as exception:
        raise ConfigError("{0} must be a number.".format(name)) from exception
    if not minimum <= value <= maximum:
        raise ConfigError(
            "{0} must be between {1} and {2}.".format(name, minimum, maximum)
        )
    return value


def _boolean(name: str, *, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ConfigError("{0} must be true or false.".format(name))


def _valid_device_id(value: str) -> bool:
    if not value or not value[0].isalnum():
        return False
    return all(character.isalnum() or character in "._-" for character in value)
