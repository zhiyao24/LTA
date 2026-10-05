"""Tests for transport-neutral authentication and mock BLE framing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.transports.base import (
    DuplicateMessageError,
    ExpiredMessageError,
    IncompleteMessageError,
    MessageAuthenticationError,
    MessageValidationError,
    TransportUnavailableError,
    build_authenticated_message,
    decode_authenticated_message,
    encode_message,
)
from backend.app.transports.bluetooth import (
    DEFAULT_ATT_PAYLOAD_BYTES,
    LTA_BLE_SERVICE_UUID,
    LTA_COMMAND_CHARACTERISTIC_UUID,
    LTA_EVENT_CHARACTERISTIC_UUID,
    MockBluetoothTransport,
    fragment_message,
)
from backend.app.transports.wifi import WifiTransport


DEVICE_TOKEN = "transport-test-device-token"
DEVICE_ID = "jetson-transport-test"


def _message(
    *,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    payload: dict | None = None,
):
    created = created_at or datetime.now(timezone.utc)
    expiry = expires_at or created + timedelta(seconds=30)
    command_id = str(uuid4())
    return build_authenticated_message(
        message_type="command",
        message_id=command_id,
        correlation_id=None,
        device_id=DEVICE_ID,
        created_at=created,
        expires_at=expiry,
        payload=payload
        or {
            "id": command_id,
            "device_id": DEVICE_ID,
            "command_type": "STOP",
            "payload": {},
            "status": "delivered",
            "expires_at": expiry.isoformat(),
            "simulation_only": True,
        },
        device_token=DEVICE_TOKEN,
    )


def test_wifi_adapter_preserves_one_message_per_packet_and_rejects_replay() -> None:
    transport = WifiTransport(device_token=DEVICE_TOKEN)
    transport.connect()
    packet = transport.encode_outbound(_message())[0]

    decoded = transport.receive_packet(packet)

    assert decoded["protocol_version"] == 1
    assert decoded["message_type"] == "command"
    with pytest.raises(DuplicateMessageError):
        transport.receive_packet(packet)


def test_transport_requires_connection() -> None:
    transport = WifiTransport(device_token=DEVICE_TOKEN)

    with pytest.raises(TransportUnavailableError):
        transport.encode_outbound(_message())


def test_message_authentication_rejects_wrong_token_and_tampering() -> None:
    encoded = encode_message(_message())

    with pytest.raises(MessageAuthenticationError):
        decode_authenticated_message(encoded, device_token="wrong-device-token")

    tampered = encoded.replace(b'"STOP"', b'"NOPE"')
    with pytest.raises(MessageAuthenticationError):
        decode_authenticated_message(tampered, device_token=DEVICE_TOKEN)


def test_expired_message_is_rejected() -> None:
    checked_at = datetime.now(timezone.utc)
    message = _message(
        created_at=checked_at - timedelta(seconds=2),
        expires_at=checked_at - timedelta(seconds=1),
    )

    with pytest.raises(ExpiredMessageError):
        decode_authenticated_message(
            encode_message(message),
            device_token=DEVICE_TOKEN,
            now=checked_at,
        )


def test_mock_ble_fragments_fit_conservative_att_limit_and_reassemble() -> None:
    transport = MockBluetoothTransport(device_token=DEVICE_TOKEN)
    transport.connect()
    packets = transport.encode_outbound(_message())

    assert len(packets) > 1
    assert all(len(packet) <= DEFAULT_ATT_PAYLOAD_BYTES for packet in packets)
    completed = None
    for packet in packets:
        completed = transport.receive_packet(packet)

    assert completed is not None
    assert completed["message_type"] == "command"


def test_mock_ble_rejects_incomplete_duplicate_and_malformed_fragments() -> None:
    transport = MockBluetoothTransport(device_token=DEVICE_TOKEN)
    transport.connect()
    packets = transport.encode_outbound(_message())
    assert transport.receive_packet(packets[0]) is None

    with pytest.raises(DuplicateMessageError):
        transport.receive_packet(packets[0])

    transport.disconnect()
    transport.connect()
    transport.receive_packet(packets[0])
    with pytest.raises(IncompleteMessageError):
        transport.reject_incomplete()

    with pytest.raises(MessageValidationError):
        transport.receive_packet(b"too-short")


def test_mock_ble_reconnect_attempts_are_bounded() -> None:
    eventually_connected = MockBluetoothTransport(
        device_token=DEVICE_TOKEN,
        simulated_connection_failures=2,
        maximum_reconnect_attempts=3,
    )
    eventually_connected.connect()
    assert eventually_connected.connection_attempts == 3

    unavailable = MockBluetoothTransport(
        device_token=DEVICE_TOKEN,
        simulated_connection_failures=10,
        maximum_reconnect_attempts=3,
    )
    with pytest.raises(TransportUnavailableError, match="bounded attempts"):
        unavailable.connect()
    assert unavailable.connection_attempts == 3


def test_ble_protocol_rejects_oversized_messages() -> None:
    with pytest.raises(MessageValidationError, match="protocol limit"):
        fragment_message(b"x" * 4097)


def test_documented_gatt_uuids_match_backend_constants() -> None:
    documentation = (
        Path(__file__).resolve().parents[2] / "docs" / "bluetooth.md"
    ).read_text(encoding="utf-8")

    assert LTA_BLE_SERVICE_UUID in documentation
    assert LTA_COMMAND_CHARACTERISTIC_UUID in documentation
    assert LTA_EVENT_CHARACTERISTIC_UUID in documentation
