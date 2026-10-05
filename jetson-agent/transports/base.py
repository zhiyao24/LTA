"""Common Jetson transport contract and authenticated JSON protocol.

The code avoids third-party dependencies and modern-only Python features so it
can be copied to older Jetson Python environments after their version is known.
"""

import hashlib
import hmac
import json
from abc import ABCMeta, abstractmethod
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional, Set
from uuid import UUID

from http_transport import (
    AuthenticationTransportError,
    ProtocolTransportError,
)


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


class DuplicateTransportMessageError(ProtocolTransportError):
    """A previously authenticated message or fragment was repeated."""


class ExpiredTransportMessageError(ProtocolTransportError):
    """A message expiry time has passed."""


class IncompleteTransportMessageError(ProtocolTransportError):
    """A fragmented message was not completed."""


class ReplayGuard:
    """Keep a bounded record of authenticated message IDs."""

    def __init__(self, maximum_entries=1000):
        if maximum_entries < 1:
            raise ValueError("maximum_entries must be at least 1")
        self._maximum_entries = maximum_entries
        self._ordered_ids = deque()  # type: Deque[str]
        self._ids = set()  # type: Set[str]

    def check_and_mark(self, message_id):
        if message_id in self._ids:
            raise DuplicateTransportMessageError("Message ID was already accepted")
        self._ordered_ids.append(message_id)
        self._ids.add(message_id)
        while len(self._ordered_ids) > self._maximum_entries:
            self._ids.remove(self._ordered_ids.popleft())


class AgentTransport(metaclass=ABCMeta):
    """Operations the polling agent needs regardless of the wire transport."""

    @abstractmethod
    def send_heartbeat(self, *, device_timestamp):
        raise NotImplementedError

    @abstractmethod
    def send_telemetry(self, *, device_timestamp, data):
        raise NotImplementedError

    @abstractmethod
    def poll_next(self):
        raise NotImplementedError

    @abstractmethod
    def acknowledge(
        self,
        command_id,
        *,
        acknowledgement_id,
        status,
        result,
    ):
        raise NotImplementedError


def build_authenticated_message(
    *,
    message_type,
    message_id,
    correlation_id,
    device_id,
    created_at,
    expires_at,
    payload,
    device_token,
):
    """Create the same version-one signed JSON envelope used by FastAPI."""

    if not device_token:
        raise AuthenticationTransportError("A non-empty device token is required")
    normalized_message_id = _canonical_uuid(message_id, "message_id")
    normalized_correlation_id = (
        _canonical_uuid(correlation_id, "correlation_id")
        if correlation_id is not None
        else None
    )
    _validate_type_and_correlation(message_type, normalized_correlation_id)
    _validate_device_id(device_id)
    created_text = _utc_text(created_at, "created_at")
    expires_text = _utc_text(expires_at, "expires_at")
    if expires_at.astimezone(timezone.utc) <= created_at.astimezone(timezone.utc):
        raise ProtocolTransportError("expires_at must be later than created_at")

    unsigned = {
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
    message = dict(unsigned)
    message["authentication"] = {
        "scheme": AUTHENTICATION_SCHEME,
        "signature": signature,
    }
    encode_message(message)
    return message


def encode_message(message):
    try:
        encoded = _canonical_json(message)
    except (TypeError, ValueError) as exception:
        raise ProtocolTransportError(
            "Message must contain valid JSON values"
        ) from exception
    if len(encoded) > MAX_MESSAGE_BYTES:
        raise ProtocolTransportError(
            "Message exceeds the {0}-byte protocol limit".format(MAX_MESSAGE_BYTES)
        )
    return encoded


def decode_authenticated_message(
    encoded,
    *,
    device_token,
    replay_guard=None,
    now=None,
):
    """Authenticate, validate, and optionally replay-protect one message."""

    if not device_token:
        raise AuthenticationTransportError("A non-empty device token is required")
    if not encoded or len(encoded) > MAX_MESSAGE_BYTES:
        raise ProtocolTransportError("Message is empty or exceeds the protocol limit")
    try:
        decoded = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exception:
        raise ProtocolTransportError("Message must be valid UTF-8 JSON") from exception
    if not isinstance(decoded, dict) or set(decoded) != MESSAGE_FIELDS:
        raise ProtocolTransportError("Message contains missing or unexpected fields")

    authentication = decoded.get("authentication")
    if not isinstance(authentication, dict) or set(authentication) != {
        "scheme",
        "signature",
    }:
        raise AuthenticationTransportError("Message authentication is malformed")
    if authentication.get("scheme") != AUTHENTICATION_SCHEME:
        raise AuthenticationTransportError(
            "Message authentication scheme is unsupported"
        )
    supplied_signature = authentication.get("signature")
    if not isinstance(supplied_signature, str) or len(supplied_signature) != 64:
        raise AuthenticationTransportError("Message signature is malformed")

    unsigned = dict(
        (key, value) for key, value in decoded.items() if key != "authentication"
    )
    expected_signature = hmac.new(
        device_token.encode("utf-8"),
        _canonical_json(unsigned),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise AuthenticationTransportError("Message signature is invalid")

    if decoded.get("protocol_version") != PROTOCOL_VERSION:
        raise ProtocolTransportError("Message protocol version is unsupported")
    message_type = decoded.get("message_type")
    if not isinstance(message_type, str):
        raise ProtocolTransportError("message_type must be a string")
    message_id = _canonical_uuid(decoded.get("message_id"), "message_id")
    correlation_value = decoded.get("correlation_id")
    correlation_id = (
        _canonical_uuid(correlation_value, "correlation_id")
        if correlation_value is not None
        else None
    )
    _validate_type_and_correlation(message_type, correlation_id)
    _validate_device_id(decoded.get("device_id"))
    if not isinstance(decoded.get("payload"), dict):
        raise ProtocolTransportError("payload must be a JSON object")

    created_at = _parse_timestamp(decoded.get("created_at"), "created_at")
    expires_at = _parse_timestamp(decoded.get("expires_at"), "expires_at")
    if expires_at <= created_at:
        raise ProtocolTransportError("expires_at must be later than created_at")
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("now must include a timezone")
    if expires_at <= checked_at.astimezone(timezone.utc):
        raise ExpiredTransportMessageError("Message has expired")

    if replay_guard is not None:
        replay_guard.check_and_mark(message_id)
    return decoded


def _canonical_json(value):
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_uuid(value, field_name):
    if not isinstance(value, str):
        raise ProtocolTransportError(
            "{0} must be a UUID string".format(field_name)
        )
    try:
        normalized = str(UUID(value))
    except (ValueError, AttributeError) as exception:
        raise ProtocolTransportError(
            "{0} must be a valid UUID".format(field_name)
        ) from exception
    if normalized != value.lower():
        raise ProtocolTransportError(
            "{0} must use canonical UUID formatting".format(field_name)
        )
    return normalized


def _validate_type_and_correlation(message_type, correlation_id):
    if message_type not in ALLOWED_MESSAGE_TYPES:
        raise ProtocolTransportError("message_type is not allowlisted")
    if message_type == "acknowledgement" and correlation_id is None:
        raise ProtocolTransportError(
            "Acknowledgements require a command correlation_id"
        )
    if message_type != "acknowledgement" and correlation_id is not None:
        raise ProtocolTransportError("Only acknowledgements may use correlation_id")


def _validate_device_id(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ProtocolTransportError("device_id must contain 1 to 64 characters")
    if not value[0].isalnum() or not all(
        character.isalnum() or character in "._-" for character in value
    ):
        raise ProtocolTransportError("device_id contains unsupported characters")


def _utc_text(value, field_name):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProtocolTransportError(
            "{0} must include a timezone".format(field_name)
        )
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value, field_name):
    if not isinstance(value, str):
        raise ProtocolTransportError(
            "{0} must be an ISO 8601 timestamp".format(field_name)
        )
    try:
        if value.endswith("Z"):
            timestamp_text = value[:-1]
            offset = timezone.utc
        elif len(value) >= 6 and value[-6] in {"+", "-"} and value[-3] == ":":
            sign = 1 if value[-6] == "+" else -1
            offset_hours = int(value[-5:-3])
            offset_minutes = int(value[-2:])
            if offset_hours > 23 or offset_minutes > 59:
                raise ValueError("invalid UTC offset")
            offset = timezone(
                sign * timedelta(hours=offset_hours, minutes=offset_minutes)
            )
            timestamp_text = value[:-6]
        else:
            raise ValueError("timezone missing")
        parsed = _parse_without_offset(timestamp_text).replace(tzinfo=offset)
    except ValueError as exception:
        raise ProtocolTransportError(
            "{0} must be an ISO 8601 timestamp".format(field_name)
        ) from exception
    return parsed.astimezone(timezone.utc)


def _parse_without_offset(value):
    for timestamp_format in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, timestamp_format)
        except ValueError:
            continue
    raise ValueError("invalid datetime")
