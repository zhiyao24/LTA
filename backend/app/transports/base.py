"""Common authenticated message format used by optional transports."""

from __future__ import annotations

import hashlib
import hmac
import json
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 4096
AUTHENTICATION_SCHEME = "hmac-sha256"
ALLOWED_MESSAGE_TYPES = frozenset(
    {"command", "acknowledgement", "heartbeat", "telemetry"}
)
MESSAGE_FIELDS = frozenset(
    {
        "protocol_version",
        "message_type",
        "message_id",
        "correlation_id",
        "device_id",
        "created_at",
        "expires_at",
        "payload",
        "authentication",
    }
)


class TransportError(RuntimeError):
    """Base class for safe transport-layer errors."""


class TransportUnavailableError(TransportError):
    """The requested transport is unavailable or disconnected."""


class MessageValidationError(TransportError):
    """A transport message is malformed or violates the protocol."""


class MessageAuthenticationError(MessageValidationError):
    """A message signature does not match the configured device token."""


class DuplicateMessageError(MessageValidationError):
    """A previously accepted message or fragment was received again."""


class ExpiredMessageError(MessageValidationError):
    """A message expiry time has passed."""


class IncompleteMessageError(MessageValidationError):
    """A fragmented message did not finish within its bounded lifetime."""


class ReplayGuard:
    """Keep a bounded process-local set of authenticated message IDs."""

    def __init__(self, maximum_entries: int = 1000) -> None:
        if maximum_entries < 1:
            raise ValueError("maximum_entries must be at least 1")
        self._maximum_entries = maximum_entries
        self._ordered_ids: deque[str] = deque()
        self._ids: set[str] = set()

    def check_and_mark(self, message_id: str) -> None:
        if message_id in self._ids:
            raise DuplicateMessageError("Message ID was already accepted")
        self._ordered_ids.append(message_id)
        self._ids.add(message_id)
        while len(self._ordered_ids) > self._maximum_entries:
            self._ids.remove(self._ordered_ids.popleft())


class BaseTransport(ABC):
    """Small interface shared by Wi-Fi and mock BLE transport adapters."""

    name: str

    @abstractmethod
    def connect(self) -> None:
        """Prepare the transport without weakening authentication."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the transport and discard incomplete state."""

    @abstractmethod
    def encode_outbound(self, message: Mapping[str, Any]) -> list[bytes]:
        """Encode one authenticated message into transport packets."""

    @abstractmethod
    def receive_packet(self, packet: bytes) -> dict[str, Any] | None:
        """Accept one packet and return a complete validated message if ready."""


def build_authenticated_message(
    *,
    message_type: str,
    message_id: str,
    correlation_id: str | None,
    device_id: str,
    created_at: datetime,
    expires_at: datetime,
    payload: Mapping[str, Any],
    device_token: str,
) -> dict[str, Any]:
    """Create a version-one JSON message signed with the device-only token."""

    if not device_token:
        raise MessageAuthenticationError("A non-empty device token is required")
    normalized_message_id = _canonical_uuid(message_id, "message_id")
    normalized_correlation_id = (
        _canonical_uuid(correlation_id, "correlation_id")
        if correlation_id is not None
        else None
    )
    _validate_message_type_and_correlation(message_type, normalized_correlation_id)
    _validate_device_id(device_id)
    created_text = _utc_text(created_at, "created_at")
    expires_text = _utc_text(expires_at, "expires_at")
    if expires_at.astimezone(timezone.utc) <= created_at.astimezone(timezone.utc):
        raise MessageValidationError("expires_at must be later than created_at")

    unsigned: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "message_type": message_type,
        "message_id": normalized_message_id,
        "correlation_id": normalized_correlation_id,
        "device_id": device_id,
        "created_at": created_text,
        "expires_at": expires_text,
        "payload": dict(payload),
    }
    signature = hmac.new(
        device_token.encode("utf-8"),
        _canonical_json(unsigned),
        hashlib.sha256,
    ).hexdigest()
    message = {
        **unsigned,
        "authentication": {
            "scheme": AUTHENTICATION_SCHEME,
            "signature": signature,
        },
    }
    encode_message(message)
    return message


def encode_message(message: Mapping[str, Any]) -> bytes:
    """Serialize one message and enforce the protocol-wide size ceiling."""

    try:
        encoded = _canonical_json(message)
    except (TypeError, ValueError) as exception:
        raise MessageValidationError("Message must contain valid JSON values") from exception
    if len(encoded) > MAX_MESSAGE_BYTES:
        raise MessageValidationError(
            f"Message exceeds the {MAX_MESSAGE_BYTES}-byte protocol limit"
        )
    return encoded


def decode_authenticated_message(
    encoded: bytes,
    *,
    device_token: str,
    replay_guard: ReplayGuard | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Authenticate and validate one complete versioned JSON message."""

    if not device_token:
        raise MessageAuthenticationError("A non-empty device token is required")
    if not encoded or len(encoded) > MAX_MESSAGE_BYTES:
        raise MessageValidationError("Message is empty or exceeds the protocol limit")
    try:
        decoded = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exception:
        raise MessageValidationError("Message must be valid UTF-8 JSON") from exception
    if not isinstance(decoded, dict) or set(decoded) != MESSAGE_FIELDS:
        raise MessageValidationError("Message contains missing or unexpected fields")

    authentication = decoded.get("authentication")
    if not isinstance(authentication, dict) or set(authentication) != {
        "scheme",
        "signature",
    }:
        raise MessageAuthenticationError("Message authentication is malformed")
    if authentication.get("scheme") != AUTHENTICATION_SCHEME:
        raise MessageAuthenticationError("Message authentication scheme is unsupported")
    supplied_signature = authentication.get("signature")
    if not isinstance(supplied_signature, str) or len(supplied_signature) != 64:
        raise MessageAuthenticationError("Message signature is malformed")

    unsigned = {key: value for key, value in decoded.items() if key != "authentication"}
    expected_signature = hmac.new(
        device_token.encode("utf-8"),
        _canonical_json(unsigned),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise MessageAuthenticationError("Message signature is invalid")

    if decoded.get("protocol_version") != PROTOCOL_VERSION:
        raise MessageValidationError("Message protocol version is unsupported")
    message_type = decoded.get("message_type")
    if not isinstance(message_type, str):
        raise MessageValidationError("message_type must be a string")
    message_id = _canonical_uuid(decoded.get("message_id"), "message_id")
    correlation_value = decoded.get("correlation_id")
    correlation_id = (
        _canonical_uuid(correlation_value, "correlation_id")
        if correlation_value is not None
        else None
    )
    _validate_message_type_and_correlation(message_type, correlation_id)
    _validate_device_id(decoded.get("device_id"))
    if not isinstance(decoded.get("payload"), dict):
        raise MessageValidationError("payload must be a JSON object")

    created_at = _parse_timestamp(decoded.get("created_at"), "created_at")
    expires_at = _parse_timestamp(decoded.get("expires_at"), "expires_at")
    if expires_at <= created_at:
        raise MessageValidationError("expires_at must be later than created_at")
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if expires_at <= checked_at:
        raise ExpiredMessageError("Message has expired")

    if replay_guard is not None:
        replay_guard.check_and_mark(message_id)
    return decoded


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_uuid(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise MessageValidationError(f"{field_name} must be a UUID string")
    try:
        normalized = str(UUID(value))
    except (ValueError, AttributeError) as exception:
        raise MessageValidationError(f"{field_name} must be a valid UUID") from exception
    if normalized != value.lower():
        raise MessageValidationError(f"{field_name} must use canonical UUID formatting")
    return normalized


def _validate_message_type_and_correlation(
    message_type: str,
    correlation_id: str | None,
) -> None:
    if message_type not in ALLOWED_MESSAGE_TYPES:
        raise MessageValidationError("message_type is not allowlisted")
    if message_type == "acknowledgement" and correlation_id is None:
        raise MessageValidationError("Acknowledgements require a command correlation_id")
    if message_type != "acknowledgement" and correlation_id is not None:
        raise MessageValidationError("Only acknowledgements may use correlation_id")


def _validate_device_id(value: Any) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise MessageValidationError("device_id must contain 1 to 64 characters")
    if not value[0].isalnum() or not all(
        character.isalnum() or character in "._-" for character in value
    ):
        raise MessageValidationError("device_id contains unsupported characters")


def _utc_text(value: datetime, field_name: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MessageValidationError(f"{field_name} must include a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise MessageValidationError(f"{field_name} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exception:
        raise MessageValidationError(
            f"{field_name} must be an ISO 8601 timestamp"
        ) from exception
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MessageValidationError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)
