"""LTA Bus Arrival v3 fields and the smaller response used by the dashboard."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator


class LtaBus(BaseModel):
    """Blank estimates are missing data, never an arrival at zero minutes."""

    EstimatedArrival: AwareDatetime | None = None
    Monitored: Literal[0, 1] | None = None
    Load: Literal["SEA", "SDA", "LSD", ""] = ""
    Feature: Literal["WAB", ""] = ""
    Type: Literal["SD", "DD", "BD", ""] = ""

    @field_validator("EstimatedArrival", mode="before")
    @classmethod
    def parse_estimate(cls, value: object) -> object:
        if value in (None, ""):
            return None
        if not isinstance(value, (str, datetime)):
            raise ValueError("EstimatedArrival must be an ISO timestamp with timezone")
        return value

    @field_validator("Monitored", mode="before")
    @classmethod
    def parse_monitored(cls, value: object) -> object:
        return None if value == "" else value


class LtaService(BaseModel):
    ServiceNo: str = Field(pattern=r"^[A-Za-z0-9]{1,10}$")
    Operator: str = Field(min_length=1, max_length=20)
    NextBus: LtaBus = Field(default_factory=LtaBus)
    NextBus2: LtaBus = Field(default_factory=LtaBus)
    NextBus3: LtaBus = Field(default_factory=LtaBus)


class LtaArrivalPayload(BaseModel):
    BusStopCode: str = Field(pattern=r"^[0-9]{5}$")
    Services: list[LtaService] = Field(max_length=100)

    @field_validator("Services")
    @classmethod
    def unique_services(cls, services: list[LtaService]) -> list[LtaService]:
        numbers = [service.ServiceNo.upper() for service in services]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Duplicate services in provider response")
        return services


class BusEstimate(BaseModel):
    estimated_arrival: datetime | None
    monitored: bool | None
    load: str | None
    wheelchair_accessible: bool
    vehicle_type: str | None

    @classmethod
    def from_lta(cls, bus: LtaBus) -> "BusEstimate":
        return cls(
            estimated_arrival=(
                bus.EstimatedArrival.astimezone(timezone.utc)
                if bus.EstimatedArrival is not None else None
            ),
            monitored=None if bus.Monitored is None else bus.Monitored == 1,
            load=bus.Load or None,
            wheelchair_accessible=bus.Feature == "WAB",
            vehicle_type=bus.Type or None,
        )


class BusServiceArrival(BaseModel):
    service_no: str
    operator: str
    arrivals: list[BusEstimate]


class BusArrivalResponse(BaseModel):
    source: Literal["LTA DataMall"] = "LTA DataMall"
    bus_stop_code: str
    service_no: str | None
    received_at: datetime
    server_time: datetime
    refresh_interval_seconds: Literal[20] = 20
    is_stale: bool = False
    error_message: str | None = None
    services: list[BusServiceArrival]
