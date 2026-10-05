"""Minimal standard-library HTTP transport for the local Wi-Fi backend."""

import json
import socket
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


MAX_RESPONSE_BYTES = 1_000_000
TEMPORARY_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


class TransportError(RuntimeError):
    """Base class for safe transport failures."""


class TemporaryTransportError(TransportError):
    """A network or server failure that may succeed after bounded backoff."""


class AuthenticationTransportError(TransportError):
    """The backend rejected the Jetson-only token."""


class ProtocolTransportError(TransportError):
    """The backend response was invalid or permanently rejected."""


class HttpTransport:
    """Poll and acknowledge using HTTP over the configured local network URL."""

    def __init__(
        self,
        *,
        backend_url: str,
        device_id: str,
        device_token: str,
        request_timeout_seconds: float,
    ) -> None:
        self._backend_url = backend_url.rstrip("/")
        self._device_id = device_id
        self._device_token = device_token
        self._request_timeout_seconds = request_timeout_seconds

    def send_heartbeat(self, *, device_timestamp: str) -> Dict[str, Any]:
        """Tell the backend this authenticated device is still reachable."""

        path = "/api/devices/{0}/heartbeat".format(
            quote(self._device_id, safe="")
        )
        response = self._request_json(
            "POST",
            path,
            body={"device_timestamp": device_timestamp},
        )
        if response is None:
            raise ProtocolTransportError("Backend heartbeat response was empty")
        return response

    def send_telemetry(
        self,
        *,
        device_timestamp: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send allowlisted simulated telemetry as inert JSON data."""

        path = "/api/devices/{0}/telemetry".format(
            quote(self._device_id, safe="")
        )
        response = self._request_json(
            "POST",
            path,
            body={"device_timestamp": device_timestamp, "data": data},
        )
        if response is None:
            raise ProtocolTransportError("Backend telemetry response was empty")
        return response

    def poll_next(self) -> Optional[Dict[str, Any]]:
        path = "/api/devices/{0}/commands/next".format(
            quote(self._device_id, safe="")
        )
        return self._request_json("GET", path)

    def acknowledge(
        self,
        command_id: str,
        *,
        acknowledgement_id: str,
        status: str,
        result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        path = "/api/commands/{0}/acknowledge".format(quote(command_id, safe=""))
        response = self._request_json(
            "POST",
            path,
            body={
                "acknowledgement_id": acknowledgement_id,
                "device_id": self._device_id,
                "status": status,
                "result": result,
            },
        )
        if response is None:
            raise ProtocolTransportError("Backend acknowledgement response was empty")
        return response

    def _request_json(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        encoded_body = None
        headers = {
            "Accept": "application/json",
            "X-Jetson-Token": self._device_token,
        }
        if body is not None:
            encoded_body = json.dumps(
                body,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(
            self._backend_url + path,
            data=encoded_body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self._request_timeout_seconds) as response:
                if response.status == 204:
                    return None
                response_bytes = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exception:
            self._raise_http_error(exception.code)
        except (URLError, socket.timeout, TimeoutError) as exception:
            raise TemporaryTransportError(
                "Could not communicate with the local backend"
            ) from exception

        if len(response_bytes) > MAX_RESPONSE_BYTES:
            raise ProtocolTransportError("Backend response exceeded the safe size limit")
        try:
            decoded = json.loads(response_bytes.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exception:
            raise ProtocolTransportError("Backend returned invalid JSON") from exception
        if not isinstance(decoded, dict):
            raise ProtocolTransportError("Backend response must be a JSON object")
        return decoded

    @staticmethod
    def _raise_http_error(status_code: int) -> None:
        if status_code in {401, 403}:
            raise AuthenticationTransportError(
                "Backend rejected the Jetson authentication token"
            )
        if status_code in TEMPORARY_HTTP_STATUSES:
            raise TemporaryTransportError(
                "Backend temporarily unavailable with HTTP {0}".format(status_code)
            )
        raise ProtocolTransportError(
            "Backend rejected the request with HTTP {0}".format(status_code)
        )
