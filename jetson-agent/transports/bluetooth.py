"""Mock Jetson BLE GATT peripheral transport.

There is no BlueZ, D-Bus, adapter, advertising, or hardware access here. The
class models characteristic writes and notifications for protocol tests only.
"""

import math
import struct
import zlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from http_transport import TemporaryTransportError, TransportError

from .base import (
    MAX_MESSAGE_BYTES,
    AgentTransport,
    DuplicateTransportMessageError,
    IncompleteTransportMessageError,
    ReplayGuard,
    build_authenticated_message,
    decode_authenticated_message,
    encode_message,
)


LTA_BLE_SERVICE_UUID = "8f2d0001-7a4b-4a6b-9c31-2e5d4f7a1000"
LTA_COMMAND_CHARACTERISTIC_UUID = "8f2d0002-7a4b-4a6b-9c31-2e5d4f7a1000"
LTA_EVENT_CHARACTERISTIC_UUID = "8f2d0003-7a4b-4a6b-9c31-2e5d4f7a1000"

FRAME_MAGIC = 0x4C
FRAME_VERSION = 1
FRAME_HEADER = struct.Struct("!BBIHHH")
DEFAULT_ATT_PAYLOAD_BYTES = 20
MAX_RECONNECT_ATTEMPTS = 3
INCOMPLETE_MESSAGE_TIMEOUT_SECONDS = 10.0


def fragment_message(encoded, maximum_packet_bytes=DEFAULT_ATT_PAYLOAD_BYTES):
    """Create packets compatible with the backend mock BLE central."""

    if not encoded or len(encoded) > MAX_MESSAGE_BYTES:
        raise TransportError("BLE message is empty or exceeds the protocol limit")
    payload_bytes = maximum_packet_bytes - FRAME_HEADER.size
    if payload_bytes < 1:
        raise ValueError(
            "maximum_packet_bytes must be greater than {0}".format(
                FRAME_HEADER.size
            )
        )
    total_fragments = int(math.ceil(float(len(encoded)) / payload_bytes))
    if total_fragments > 65535:
        raise TransportError("BLE message requires too many fragments")
    message_token = zlib.crc32(encoded)
    packets = []
    for index in range(total_fragments):
        fragment = encoded[index * payload_bytes : (index + 1) * payload_bytes]
        packets.append(
            FRAME_HEADER.pack(
                FRAME_MAGIC,
                FRAME_VERSION,
                message_token,
                index,
                total_fragments,
                len(fragment),
            )
            + fragment
        )
    return packets


class FragmentReassembler:
    def __init__(self, incomplete_timeout_seconds=INCOMPLETE_MESSAGE_TIMEOUT_SECONDS):
        if incomplete_timeout_seconds <= 0:
            raise ValueError("incomplete_timeout_seconds must be positive")
        self._timeout = timedelta(seconds=incomplete_timeout_seconds)
        self._assemblies = {}  # type: Dict[int, Dict[str, Any]]

    def feed(self, packet, now=None):
        checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if len(packet) < FRAME_HEADER.size:
            raise TransportError("BLE fragment is shorter than its header")
        magic, version, token, index, total, declared_length = FRAME_HEADER.unpack(
            packet[: FRAME_HEADER.size]
        )
        fragment = packet[FRAME_HEADER.size :]
        if magic != FRAME_MAGIC or version != FRAME_VERSION:
            raise TransportError("BLE fragment header is unsupported")
        if total < 1 or index >= total or declared_length != len(fragment) or not fragment:
            raise TransportError("BLE fragment header is malformed")

        assembly = self._assemblies.get(token)
        if assembly is not None and checked_at - assembly["updated_at"] > self._timeout:
            del self._assemblies[token]
            raise IncompleteTransportMessageError("Incomplete BLE message expired")
        if assembly is None:
            assembly = {
                "total": total,
                "updated_at": checked_at,
                "fragments": {},
                "total_bytes": 0,
            }
            self._assemblies[token] = assembly
        elif assembly["total"] != total:
            raise TransportError("BLE fragment count changed during reassembly")

        if index in assembly["fragments"]:
            raise DuplicateTransportMessageError(
                "Duplicate BLE fragment was rejected"
            )
        assembly["fragments"][index] = fragment
        assembly["total_bytes"] += len(fragment)
        assembly["updated_at"] = checked_at
        if assembly["total_bytes"] > MAX_MESSAGE_BYTES:
            del self._assemblies[token]
            raise TransportError("Reassembled BLE message exceeds the size limit")
        if len(assembly["fragments"]) != total:
            return None

        encoded = b"".join(
            assembly["fragments"][position] for position in range(total)
        )
        del self._assemblies[token]
        if zlib.crc32(encoded) != token:
            raise TransportError("BLE message checksum does not match")
        return encoded

    def reject_incomplete(self):
        if self._assemblies:
            self._assemblies.clear()
            raise IncompleteTransportMessageError("BLE message is incomplete")

    def clear(self):
        self._assemblies.clear()


class MockGattPeripheralTransport(AgentTransport):
    """In-memory peripheral that satisfies the agent transport contract."""

    name = "bluetooth-mock"

    def __init__(
        self,
        *,
        device_id,
        device_token,
        maximum_packet_bytes=DEFAULT_ATT_PAYLOAD_BYTES,
        simulated_connection_failures=0,
        maximum_reconnect_attempts=MAX_RECONNECT_ATTEMPTS,
    ):
        if maximum_reconnect_attempts < 1 or maximum_reconnect_attempts > 10:
            raise ValueError("maximum_reconnect_attempts must be between 1 and 10")
        self._device_id = device_id
        self._device_token = device_token
        self._maximum_packet_bytes = maximum_packet_bytes
        self._remaining_connection_failures = max(0, simulated_connection_failures)
        self._maximum_reconnect_attempts = maximum_reconnect_attempts
        self._connected = False
        self._connection_attempts = 0
        self._incoming_commands = []  # type: List[Dict[str, Any]]
        self._notification_fragments = []  # type: List[bytes]
        self._reassembler = FragmentReassembler()
        self._replay_guard = ReplayGuard()

    @property
    def connection_attempts(self):
        return self._connection_attempts

    def connect(self):
        for _attempt in range(self._maximum_reconnect_attempts):
            self._connection_attempts += 1
            if self._remaining_connection_failures:
                self._remaining_connection_failures -= 1
                continue
            self._connected = True
            return
        raise TemporaryTransportError(
            "Mock BLE peripheral connection failed after bounded attempts"
        )

    def disconnect(self):
        self._connected = False
        self._reassembler.clear()
        self._incoming_commands = []
        self._notification_fragments = []
        self._replay_guard = ReplayGuard()

    def write_command_fragment(self, packet):
        self._require_connected()
        encoded = self._reassembler.feed(packet)
        if encoded is None:
            return None
        message = decode_authenticated_message(
            encoded,
            device_token=self._device_token,
            replay_guard=self._replay_guard,
        )
        if message["message_type"] != "command":
            raise TransportError("Command characteristic accepts only command messages")
        if message["device_id"] != self._device_id:
            raise TransportError("BLE message is addressed to a different device")
        command = message["payload"]
        self._incoming_commands.append(command)
        return command

    def reject_incomplete(self):
        self._reassembler.reject_incomplete()

    def drain_notification_fragments(self):
        packets = list(self._notification_fragments)
        self._notification_fragments = []
        return packets

    def send_heartbeat(self, *, device_timestamp):
        self._queue_event(
            "heartbeat",
            str(uuid4()),
            None,
            {"device_timestamp": device_timestamp},
        )
        return {"status": "online", "simulated": True}

    def send_telemetry(self, *, device_timestamp, data):
        self._queue_event(
            "telemetry",
            str(uuid4()),
            None,
            {"device_timestamp": device_timestamp, "data": dict(data)},
        )
        return {"stored": True, "simulated": True}

    def poll_next(self):
        self._require_connected()
        return self._incoming_commands.pop(0) if self._incoming_commands else None

    def acknowledge(
        self,
        command_id,
        *,
        acknowledgement_id,
        status,
        result,
    ):
        payload = {
            "acknowledgement_id": acknowledgement_id,
            "device_id": self._device_id,
            "status": status,
            "result": result,
        }
        self._queue_event(
            "acknowledgement",
            acknowledgement_id,
            command_id,
            payload,
        )
        return payload

    def _queue_event(self, message_type, message_id, correlation_id, payload):
        self._require_connected()
        created_at = datetime.now(timezone.utc)
        message = build_authenticated_message(
            message_type=message_type,
            message_id=message_id,
            correlation_id=correlation_id,
            device_id=self._device_id,
            created_at=created_at,
            expires_at=created_at + timedelta(seconds=30),
            payload=payload,
            device_token=self._device_token,
        )
        self._notification_fragments.extend(
            fragment_message(
                encode_message(message),
                maximum_packet_bytes=self._maximum_packet_bytes,
            )
        )

    def _require_connected(self):
        if not self._connected:
            raise TemporaryTransportError("Mock BLE peripheral is not connected")
