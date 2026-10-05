"""Mock BLE central transport with strict ATT fragmentation.

This module performs no scanning and imports no Bleak code. It models the wire
contract that a future Bleak implementation must follow after hardware review.
"""

from __future__ import annotations

import math
import struct
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .base import (
    MAX_MESSAGE_BYTES,
    BaseTransport,
    DuplicateMessageError,
    IncompleteMessageError,
    MessageValidationError,
    ReplayGuard,
    TransportUnavailableError,
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


@dataclass
class _Assembly:
    total_fragments: int
    updated_at: datetime
    fragments: dict[int, bytes] = field(default_factory=dict)
    total_bytes: int = 0


def fragment_message(
    encoded: bytes,
    *,
    maximum_packet_bytes: int = DEFAULT_ATT_PAYLOAD_BYTES,
) -> list[bytes]:
    """Split a complete JSON message into bounded characteristic values."""

    if not encoded or len(encoded) > MAX_MESSAGE_BYTES:
        raise MessageValidationError("BLE message is empty or exceeds the protocol limit")
    payload_bytes = maximum_packet_bytes - FRAME_HEADER.size
    if payload_bytes < 1:
        raise ValueError(
            f"maximum_packet_bytes must be greater than {FRAME_HEADER.size}"
        )
    total_fragments = math.ceil(len(encoded) / payload_bytes)
    if total_fragments > 65535:
        raise MessageValidationError("BLE message requires too many fragments")
    message_token = zlib.crc32(encoded)
    packets = []
    for index in range(total_fragments):
        fragment = encoded[index * payload_bytes : (index + 1) * payload_bytes]
        header = FRAME_HEADER.pack(
            FRAME_MAGIC,
            FRAME_VERSION,
            message_token,
            index,
            total_fragments,
            len(fragment),
        )
        packets.append(header + fragment)
    return packets


class FragmentReassembler:
    """Reassemble bounded fragments while rejecting stale or duplicate data."""

    def __init__(
        self,
        *,
        incomplete_timeout_seconds: float = INCOMPLETE_MESSAGE_TIMEOUT_SECONDS,
    ) -> None:
        if incomplete_timeout_seconds <= 0:
            raise ValueError("incomplete_timeout_seconds must be positive")
        self._timeout = timedelta(seconds=incomplete_timeout_seconds)
        self._assemblies: dict[int, _Assembly] = {}

    def feed(self, packet: bytes, *, now: datetime | None = None) -> bytes | None:
        checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if len(packet) < FRAME_HEADER.size:
            raise MessageValidationError("BLE fragment is shorter than its header")
        magic, version, token, index, total, declared_length = FRAME_HEADER.unpack(
            packet[: FRAME_HEADER.size]
        )
        fragment = packet[FRAME_HEADER.size :]
        if magic != FRAME_MAGIC or version != FRAME_VERSION:
            raise MessageValidationError("BLE fragment header is unsupported")
        if total < 1 or index >= total or declared_length != len(fragment) or not fragment:
            raise MessageValidationError("BLE fragment header is malformed")

        assembly = self._assemblies.get(token)
        if assembly is not None and checked_at - assembly.updated_at > self._timeout:
            del self._assemblies[token]
            raise IncompleteMessageError("Incomplete BLE message expired")
        if assembly is None:
            assembly = _Assembly(total_fragments=total, updated_at=checked_at)
            self._assemblies[token] = assembly
        elif assembly.total_fragments != total:
            raise MessageValidationError("BLE fragment count changed during reassembly")

        if index in assembly.fragments:
            raise DuplicateMessageError("Duplicate BLE fragment was rejected")
        assembly.fragments[index] = fragment
        assembly.total_bytes += len(fragment)
        assembly.updated_at = checked_at
        if assembly.total_bytes > MAX_MESSAGE_BYTES:
            del self._assemblies[token]
            raise MessageValidationError("Reassembled BLE message exceeds the size limit")
        if len(assembly.fragments) != total:
            return None

        encoded = b"".join(assembly.fragments[position] for position in range(total))
        del self._assemblies[token]
        if zlib.crc32(encoded) != token:
            raise MessageValidationError("BLE message checksum does not match")
        return encoded

    def reject_incomplete(self) -> None:
        if self._assemblies:
            self._assemblies.clear()
            raise IncompleteMessageError("BLE message is incomplete")

    def clear(self) -> None:
        self._assemblies.clear()


class MockBluetoothTransport(BaseTransport):
    """In-memory BLE central used for protocol tests only—not real Bleak I/O."""

    name = "bluetooth-mock"

    def __init__(
        self,
        *,
        device_token: str,
        maximum_packet_bytes: int = DEFAULT_ATT_PAYLOAD_BYTES,
        simulated_connection_failures: int = 0,
        maximum_reconnect_attempts: int = MAX_RECONNECT_ATTEMPTS,
    ) -> None:
        if maximum_reconnect_attempts < 1 or maximum_reconnect_attempts > 10:
            raise ValueError("maximum_reconnect_attempts must be between 1 and 10")
        self._device_token = device_token
        self._maximum_packet_bytes = maximum_packet_bytes
        self._remaining_connection_failures = max(0, simulated_connection_failures)
        self._maximum_reconnect_attempts = maximum_reconnect_attempts
        self._connected = False
        self._connection_attempts = 0
        self._reassembler = FragmentReassembler()
        self._replay_guard = ReplayGuard()

    @property
    def connection_attempts(self) -> int:
        return self._connection_attempts

    def connect(self) -> None:
        for _attempt in range(self._maximum_reconnect_attempts):
            self._connection_attempts += 1
            if self._remaining_connection_failures:
                self._remaining_connection_failures -= 1
                continue
            self._connected = True
            return
        raise TransportUnavailableError(
            "Mock BLE connection failed after bounded attempts"
        )

    def disconnect(self) -> None:
        self._connected = False
        self._reassembler.clear()
        self._replay_guard = ReplayGuard()

    def encode_outbound(self, message: Mapping[str, Any]) -> list[bytes]:
        self._require_connected()
        return fragment_message(
            encode_message(message),
            maximum_packet_bytes=self._maximum_packet_bytes,
        )

    def receive_packet(self, packet: bytes) -> dict[str, Any] | None:
        self._require_connected()
        encoded = self._reassembler.feed(packet)
        if encoded is None:
            return None
        return decode_authenticated_message(
            encoded,
            device_token=self._device_token,
            replay_guard=self._replay_guard,
        )

    def reject_incomplete(self) -> None:
        self._reassembler.reject_incomplete()

    def _require_connected(self) -> None:
        if not self._connected:
            raise TransportUnavailableError("Mock BLE transport is not connected")
