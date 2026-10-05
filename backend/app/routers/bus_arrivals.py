"""Public, cached bus-arrival reads. Hardware command authentication is unchanged."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from ..schemas.bus_arrivals import BusArrivalResponse


router = APIRouter(prefix="/api/bus-arrivals", tags=["Bus arrivals"])


@router.get("", response_model=BusArrivalResponse)
def bus_arrivals(
    request: Request,
    response: Response,
    bus_stop_code: Annotated[str, Query(pattern=r"^[0-9]{5}$", description="Five digits, including any leading zero")],
    service_no: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9]{1,10}$", description="Optional service, e.g. 15 or 225G")] = None,
) -> BusArrivalResponse:
    """Fetch at most once per 20 seconds for this stop/service; preserve failed-refresh data."""
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.bus_arrival_service.get_arrivals(bus_stop_code, service_no)
