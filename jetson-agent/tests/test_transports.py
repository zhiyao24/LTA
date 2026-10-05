"""Cross-platform tests for Wi-Fi compatibility and mock GATT behavior."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest


AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from agent import JetsonAgent, build_agent  # noqa: E402
from config import AgentConfig  # noqa: E402
from handlers import HandlerRegistry  # noqa: E402
from http_transport import TemporaryTransportError  # noqa: E402
from transports.base import (  # noqa: E402
    AgentTransport,
    DuplicateTransportMessageError,
    ExpiredTransportMessageError,
)
from transports.bluetooth import (  # noqa: E402
    IncompleteTransportMessageError,
    MockGattPeripheralTransport,
)
from transports.wifi import WifiTransport  # noqa: E402

from backend.app.transports.base import (  # noqa: E402
    build_authenticated_message,
)
from backend.app.transports.bluetooth import (  # noqa: E402
    LTA_COMMAND_CHARACTERISTIC_UUID as BACKEND_COMMAND_UUID,
    LTA_EVENT_CHARACTERISTIC_UUID as BACKEND_EVENT_UUID,
    LTA_BLE_SERVICE_UUID as BACKEND_SERVICE_UUID,
    MockBluetoothTransport,
)
from transports.bluetooth import (  # noqa: E402
    LTA_BLE_SERVICE_UUID as AGENT_SERVICE_UUID,
    LTA_COMMAND_CHARACTERISTIC_UUID as AGENT_COMMAND_UUID,
    LTA_EVENT_CHARACTERISTIC_UUID as AGENT_EVENT_UUID,
)


DEVICE_ID = "jetson-ble-mock"
DEVICE_TOKEN = "ble-mock-device-token"


def _command_message(*, created_at=None, expires_at=None):
    created = created_at or datetime.now(timezone.utc)
    expiry = expires_at or created + timedelta(seconds=30)
    command_id = str(uuid4())
    raw_command = {
        "id": command_id,
        "device_id": DEVICE_ID,
        "command_type": "SET_SPEED",
        "payload": {"speed_percent": 12.5},
        "status": "delivered",
        "expires_at": expiry.isoformat(),
        "simulation_only": True,
    }
    return build_authenticated_message(
        message_type="command",
        message_id=command_id,
        correlation_id=None,
        device_id=DEVICE_ID,
        created_at=created,
        expires_at=expiry,
        payload=raw_command,
        device_token=DEVICE_TOKEN,
    )


def _connected_pair():
    central = MockBluetoothTransport(device_token=DEVICE_TOKEN)
    peripheral = MockGattPeripheralTransport(
        device_id=DEVICE_ID,
        device_token=DEVICE_TOKEN,
    )
    central.connect()
    peripheral.connect()
    return central, peripheral


def test_wifi_transport_implements_common_agent_interface() -> None:
    wifi = WifiTransport(
        backend_url="http://127.0.0.1:8000",
        device_id=DEVICE_ID,
        device_token=DEVICE_TOKEN,
        request_timeout_seconds=1,
    )

    assert isinstance(wifi, AgentTransport)
    assert wifi.name == "wifi"


def test_agent_builder_keeps_wifi_as_the_default_transport() -> None:
    agent = build_agent(AgentConfig(
        backend_url="http://127.0.0.1:8000",
        device_id=DEVICE_ID,
        device_token=DEVICE_TOKEN,
        poll_interval_seconds=1,
        request_timeout_seconds=1,
        dry_run=True,
    ))

    assert isinstance(agent.transport, WifiTransport)


def test_backend_and_agent_use_identical_documented_service_uuid() -> None:
    assert BACKEND_SERVICE_UUID == AGENT_SERVICE_UUID
    assert BACKEND_COMMAND_UUID == AGENT_COMMAND_UUID
    assert BACKEND_EVENT_UUID == AGENT_EVENT_UUID


def test_mock_ble_command_preserves_id_expiry_and_acknowledgements() -> None:
    central, peripheral = _connected_pair()
    message = _command_message()
    for packet in central.encode_outbound(message):
        peripheral.write_command_fragment(packet)

    handlers = HandlerRegistry(dry_run=True)
    agent = JetsonAgent(
        config=AgentConfig(
            backend_url="mock-ble://local",
            device_id=DEVICE_ID,
            device_token=DEVICE_TOKEN,
            poll_interval_seconds=1,
            request_timeout_seconds=1,
            dry_run=True,
        ),
        transport=peripheral,
        handlers=handlers,
        sleep=lambda _seconds: None,
    )

    assert agent.run_once() == "completed"

    received = []
    for packet in peripheral.drain_notification_fragments():
        complete = central.receive_packet(packet)
        if complete is not None:
            received.append(complete)

    acknowledgements = [
        item for item in received if item["message_type"] == "acknowledgement"
    ]
    assert {item["payload"]["status"] for item in acknowledgements} == {
        "running",
        "completed",
    }
    assert all(item["correlation_id"] == message["message_id"] for item in acknowledgements)
    assert handlers.state.outputs_enabled is False
    assert handlers.state.speed_percent == 12.5


def test_mock_peripheral_rejects_duplicate_and_expired_messages() -> None:
    central, peripheral = _connected_pair()
    packets = central.encode_outbound(_command_message())
    for packet in packets:
        peripheral.write_command_fragment(packet)

    with pytest.raises(DuplicateTransportMessageError):
        for packet in packets:
            peripheral.write_command_fragment(packet)

    checked_at = datetime.now(timezone.utc)
    expired = _command_message(
        created_at=checked_at - timedelta(seconds=2),
        expires_at=checked_at - timedelta(seconds=1),
    )
    expired_packets = central.encode_outbound(expired)
    with pytest.raises(ExpiredTransportMessageError):
        for packet in expired_packets:
            peripheral.write_command_fragment(packet)


def test_mock_peripheral_rejects_incomplete_message() -> None:
    central, peripheral = _connected_pair()
    packets = central.encode_outbound(_command_message())
    peripheral.write_command_fragment(packets[0])

    with pytest.raises(IncompleteTransportMessageError):
        peripheral.reject_incomplete()


def test_mock_peripheral_reconnection_attempts_are_bounded() -> None:
    peripheral = MockGattPeripheralTransport(
        device_id=DEVICE_ID,
        device_token=DEVICE_TOKEN,
        simulated_connection_failures=10,
        maximum_reconnect_attempts=3,
    )

    with pytest.raises(TemporaryTransportError, match="bounded attempts"):
        peripheral.connect()
    assert peripheral.connection_attempts == 3
