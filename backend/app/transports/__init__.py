"""Transport-neutral interfaces for laptop-to-Jetson communication.

Wi-Fi remains the active transport. Bluetooth classes are mock-only until
compatible hardware and BlueZ can be inspected on the target Jetson.
"""

from .base import BaseTransport
from .wifi import WifiTransport

__all__ = ["BaseTransport", "WifiTransport"]
