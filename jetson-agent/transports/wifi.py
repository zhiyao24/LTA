"""Wi-Fi implementation of the common Jetson transport interface."""

from http_transport import HttpTransport

from .base import AgentTransport


class WifiTransport(HttpTransport, AgentTransport):
    """Preserve the existing standard-library HTTP transport unchanged."""

    name = "wifi"
