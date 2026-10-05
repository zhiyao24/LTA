"""Read public bus estimates through LTA, with a shared 20-second cache."""

from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Lock

import httpx
from pydantic import ValidationError

from ..config import LTA_BUS_ARRIVAL_URL, Settings
from ..database import utc_now
from ..repositories.external_data_repository import ExternalDataRepository
from ..schemas.bus_arrivals import (
    BusArrivalResponse, BusEstimate, BusServiceArrival, LtaArrivalPayload,
)
from .external_api import ExternalApiError


REFRESH_SECONDS = 20
MAX_RETRY_ENTRIES = 128
MAX_SNAPSHOTS = 1000


class BusArrivalService:
    """Only the backend sees the AccountKey; each fetch makes one HTTPS request.

    A single lock also coalesces simultaneous requests from different browsers.
    Each stop/service has its own stored snapshot and bounded failure cooldown.
    """

    def __init__(
        self, settings: Settings, *, transport: httpx.BaseTransport | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._key = settings.lta_api_account_key
        self._timeout = httpx.Timeout(settings.external_api_timeout_seconds)
        self._transport = transport
        self._clock = clock
        self._repository = ExternalDataRepository(settings.database_path)
        self._lock = Lock()
        self._failures: OrderedDict[str, tuple[datetime, ExternalApiError]] = OrderedDict()
        self.status = "ready" if self._key else "not_configured"

    def _fetch(self, stop: str, service: str | None) -> LtaArrivalPayload:
        if not self._key:
            raise ExternalApiError(
                code="lta_not_configured", status_code=503,
                message="Add LTA_API_ACCOUNT_KEY to backend/.env and restart FastAPI.",
            )
        params = {"BusStopCode": stop}
        if service:
            params["ServiceNo"] = service
        try:
            with httpx.Client(
                timeout=self._timeout, transport=self._transport, follow_redirects=False,
            ) as client:
                response = client.get(
                    LTA_BUS_ARRIVAL_URL, params=params,
                    headers={"AccountKey": self._key, "Accept": "application/json"},
                )
        except httpx.TimeoutException:
            raise ExternalApiError(
                code="lta_timeout", status_code=504,
                message="LTA took too long to respond. Retrying after 20 seconds.",
            ) from None
        except httpx.RequestError:
            raise ExternalApiError(
                code="lta_connection_failed", status_code=503,
                message="Cannot reach LTA DataMall. Check the Mac's internet connection.",
            ) from None
        if response.status_code in (401, 403):
            raise ExternalApiError(
                code="lta_authentication_failed", status_code=502,
                message="LTA rejected the account key. Check backend/.env and restart FastAPI.",
            )
        if response.status_code == 429:
            raise ExternalApiError(
                code="lta_rate_limited", status_code=429,
                message="LTA's request limit was reached. Retrying after 20 seconds.",
            )
        if not 200 <= response.status_code < 300:
            raise ExternalApiError(
                code="lta_unavailable", status_code=502,
                message="LTA DataMall is temporarily unavailable. Please try again shortly.",
            )
        if not response.content.strip():
            raise ExternalApiError(
                code="lta_no_data", status_code=503,
                message="LTA returned no arrival data. Service availability cannot be confirmed.",
            )
        try:
            payload = LtaArrivalPayload.model_validate(response.json())
            if payload.BusStopCode != stop:
                raise ValueError("Wrong bus stop returned")
            if service and any(item.ServiceNo.upper() != service for item in payload.Services):
                raise ValueError("Wrong service returned")
            return payload
        except (ValidationError, ValueError):
            raise ExternalApiError(
                code="lta_invalid_data", status_code=502,
                message="LTA returned an unreadable arrival response. The last valid result was kept.",
            ) from None

    def get_arrivals(self, stop: str, service: str | None) -> BusArrivalResponse:
        service = service.upper() if service else None
        source = f"lta-bus-arrival:{stop}:{service or 'all'}"
        with self._lock:
            snapshot = self._repository.latest(source=source)
            now = self._clock()
            failure: ExternalApiError | None = None
            if source in self._failures:
                retry_at, previous_error = self._failures[source]
                if now < retry_at:
                    failure = previous_error
                else:
                    del self._failures[source]
            fresh = snapshot is not None and 0 <= (now - snapshot.received_at).total_seconds() < REFRESH_SECONDS
            if not fresh and failure is None:
                try:
                    payload = self._fetch(stop, service)
                    snapshot = self._repository.create(
                        source=source, data=payload.model_dump(mode="json"),
                        received_at=self._clock(),
                    )
                    self._repository.prune_bus_arrivals(keep=MAX_SNAPSHOTS)
                    self.status = "online"
                    self._failures.pop(source, None)
                except ExternalApiError as error:
                    failure = error
                    self.status = "degraded" if self._key else "not_configured"
                    self._failures[source] = (self._clock() + timedelta(seconds=REFRESH_SECONDS), error)
                    self._failures.move_to_end(source)
                    while len(self._failures) > MAX_RETRY_ENTRIES:
                        self._failures.popitem(last=False)
            if snapshot is None:
                assert failure is not None
                raise failure
            stored = LtaArrivalPayload.model_validate(snapshot.data)
            return BusArrivalResponse(
                bus_stop_code=stop, service_no=service,
                received_at=snapshot.received_at, server_time=self._clock(),
                is_stale=failure is not None,
                error_message=failure.message if failure else None,
                services=[
                    BusServiceArrival(
                        service_no=item.ServiceNo, operator=item.Operator,
                        arrivals=[BusEstimate.from_lta(bus) for bus in (item.NextBus, item.NextBus2, item.NextBus3)],
                    ) for item in stored.Services
                ],
            )
