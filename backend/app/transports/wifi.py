"""Compatibility adapter for the existing HTTP-over-Wi-Fi message path."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .base import (
    BaseTransport,
    ReplayGuard,
    TransportUnavailableError,
    decode_authenticated_message,
    encode_message,
)


class WifiTransport(BaseTransport):
    """Represent one-message-per-request transport without changing API routes.

    The working FastAPI endpoints and Jetson ``HttpTransport`` continue to own
    actual HTTP I/O. This adapter supplies the common authenticated codec for
    future service-level transport selection.
    """

    name = "wifi"

    def __init__(self, *, device_token: str) -> None:
        self._device_token = device_token
        self._connected = False
        self._replay_guard = ReplayGuard()

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False
        self._replay_guard = ReplayGuard()

    def encode_outbound(self, message: Mapping[str, Any]) -> list[bytes]:
        self._require_connected()
        return [encode_message(message)]

    def receive_packet(self, packet: bytes) -> dict[str, Any]:
        self._require_connected()
        return decode_authenticated_message(
            packet,
            device_token=self._device_token,
            replay_guard=self._replay_guard,
        )

    def _require_connected(self) -> None:
        if not self._connected:
            raise TransportUnavailableError("Wi-Fi transport is not connected")
