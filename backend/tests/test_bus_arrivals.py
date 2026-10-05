"""Provider-contract, caching and failure tests; never use a real account key."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.config import LTA_BUS_ARRIVAL_URL, Settings, get_settings
from backend.app.database import initialize_database, open_connection
from backend.app.main import create_app
from backend.app.repositories.external_data_repository import ExternalDataRepository
from backend.app.services.bus_arrivals import BusArrivalService
from backend.app.services.external_api import ExternalApiError


class Clock:
    now = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def settings(path: Path, *, key: str | None = "test-account-key") -> Settings:
    return Settings(
        app_name="Bus test", environment="test", cors_origins=("http://localhost:5173",),
        log_level="WARNING", database_path=path, lta_api_account_key=key,
    )


def payload(stop: str = "01219", service: str = "225G") -> dict:
    return {
        "BusStopCode": stop,
        "Services": [{
            "ServiceNo": service, "Operator": "SBST",
            "NextBus": {
                "EstimatedArrival": "2026-09-24T18:03:49+08:00", "Monitored": 1,
                "Load": "SEA", "Feature": "WAB", "Type": "DD",
            },
            "NextBus2": {"EstimatedArrival": "2026-09-24T18:08:00+08:00", "Monitored": 0},
            "NextBus3": {"EstimatedArrival": "", "Monitored": 0, "Load": "", "Feature": "", "Type": ""},
        }],
    }


def make_service(path: Path, handler, clock: Clock | None = None) -> BusArrivalService:
    initialize_database(path)
    return BusArrivalService(settings(path), transport=httpx.MockTransport(handler), clock=clock or Clock())


def test_lta_account_header_query_and_utc_normalization(tmp_path: Path, caplog) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(LTA_BUS_ARRIVAL_URL)
        assert request.url.scheme == "https"
        assert request.headers["AccountKey"] == "test-account-key"
        assert "Authorization" not in request.headers
        assert dict(request.url.params) == {"BusStopCode": "01219", "ServiceNo": "225G"}
        return httpx.Response(200, json=payload())

    service = make_service(tmp_path / "bus.db", handle)
    result = service.get_arrivals("01219", "225g")
    assert result.refresh_interval_seconds == 20
    assert result.services[0].arrivals[0].estimated_arrival == datetime(2026, 9, 24, 10, 3, 49, tzinfo=timezone.utc)
    assert result.services[0].arrivals[0].monitored is True
    assert result.services[0].arrivals[1].monitored is False
    assert result.services[0].arrivals[2].estimated_arrival is None
    assert "test-account-key" not in result.model_dump_json()
    assert "test-account-key" not in caplog.text
    snapshot = ExternalDataRepository(tmp_path / "bus.db").latest()
    assert snapshot is not None and snapshot.source == "lta-bus-arrival:01219:225G"
    assert "test-account-key" not in str(snapshot.data)


def test_twenty_second_cache_shared_by_concurrent_users(tmp_path: Path) -> None:
    calls = []
    clock = Clock()

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=payload())

    service = make_service(tmp_path / "cache.db", handle, clock)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.get_arrivals("01219", "225G"), range(8)))
    assert len(calls) == 1
    assert len({result.received_at for result in results}) == 1
    clock.advance(19)
    service.get_arrivals("01219", "225G")
    assert len(calls) == 1
    clock.advance(1)
    result = service.get_arrivals("01219", "225G")
    assert len(calls) == 2 and result.received_at == clock.now


@pytest.mark.parametrize("kind,code", [
    ("timeout", "lta_timeout"), ("connection", "lta_connection_failed"),
    ("401", "lta_authentication_failed"), ("403", "lta_authentication_failed"),
    ("429", "lta_rate_limited"), ("500", "lta_unavailable"),
    ("302", "lta_unavailable"), ("invalid_json", "lta_invalid_data"),
    ("invalid_schema", "lta_invalid_data"), ("empty_body", "lta_no_data"),
])
def test_failures_preserve_query_snapshot_and_have_bounded_retries(tmp_path: Path, kind: str, code: str) -> None:
    clock = Clock()
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json=payload())
        if kind == "timeout":
            raise httpx.ReadTimeout("private provider details", request=request)
        if kind == "connection":
            raise httpx.ConnectError("private provider details", request=request)
        if kind == "invalid_json":
            return httpx.Response(200, text="private provider details")
        if kind == "invalid_schema":
            return httpx.Response(200, json={"Services": "wrong"})
        if kind == "empty_body":
            return httpx.Response(204)
        return httpx.Response(int(kind), json={"error": "private provider details"}, headers={"Location": "https://elsewhere.invalid"})

    service = make_service(tmp_path / "failed.db", handle, clock)
    original = service.get_arrivals("01219", "225G")
    clock.advance(20)
    stale = service.get_arrivals("01219", "225G")
    assert stale.is_stale and stale.error_message
    assert stale.received_at == original.received_at
    assert stale.services == original.services
    assert "private provider details" not in stale.model_dump_json()
    assert service._failures["lta-bus-arrival:01219:225G"][1].code == code
    for _ in range(5):
        service.get_arrivals("01219", "225G")
    assert len(calls) == 2
    clock.advance(20)
    service.get_arrivals("01219", "225G")
    assert len(calls) == 3


def test_new_search_never_reuses_another_stops_snapshot(tmp_path: Path) -> None:
    def handle(request):
        if request.url.params["BusStopCode"] == "01219":
            return httpx.Response(200, json=payload())
        return httpx.Response(500)

    service = make_service(tmp_path / "isolated.db", handle)
    service.get_arrivals("01219", "225G")
    with pytest.raises(ExternalApiError, match="temporarily unavailable"):
        service.get_arrivals("83139", "15")


def test_all_services_and_empty_estimates_are_valid(tmp_path: Path) -> None:
    def handle(request):
        assert "ServiceNo" not in request.url.params
        return httpx.Response(200, json={"BusStopCode": "01219", "Services": []})

    service = make_service(tmp_path / "empty.db", handle)
    result = service.get_arrivals("01219", None)
    assert result.services == [] and not result.is_stale


@pytest.mark.parametrize("change", ["wrong_stop", "wrong_service", "naive_time", "numeric_time", "bad_time", "duplicate"])
def test_malformed_provider_fields_never_enter_sqlite(tmp_path: Path, change: str) -> None:
    data = payload()
    if change == "wrong_stop":
        data["BusStopCode"] = "99999"
    elif change == "wrong_service":
        data["Services"][0]["ServiceNo"] = "99"
    elif change == "duplicate":
        data["Services"].append(data["Services"][0])
    else:
        data["Services"][0]["NextBus"]["EstimatedArrival"] = {
            "naive_time": "2026-09-24T18:03:49", "numeric_time": 1234, "bad_time": "not a date",
        }[change]
    path = tmp_path / "invalid.db"
    service = make_service(path, lambda _: httpx.Response(200, json=data))
    with pytest.raises(ExternalApiError) as failure:
        service.get_arrivals("01219", "225G")
    assert failure.value.code == "lta_invalid_data"
    assert ExternalDataRepository(path).latest() is None


def test_query_validation_and_structured_error_without_key(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path / "routes.db", key=None))) as client:
        for query in ["bus_stop_code=1219", "bus_stop_code=123456", "bus_stop_code=abcde", "bus_stop_code=01219&service_no=x%3Bwhoami"]:
            response = client.get(f"/api/bus-arrivals?{query}")
            assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"
        response = client.get("/api/bus-arrivals?bus_stop_code=01219&service_no=225G")
        assert response.status_code == 503 and response.json()["error"]["code"] == "lta_not_configured"


def test_public_bus_route_does_not_bypass_command_authentication(tmp_path: Path) -> None:
    config = settings(tmp_path / "public.db")
    app = create_app(config)
    app.state.bus_arrival_service = BusArrivalService(config, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload())))
    with TestClient(app) as client:
        response = client.get("/api/bus-arrivals?bus_stop_code=01219&service_no=225G")
        assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
        assert client.get("/api/status").json()["external_api_status"] == "online"
        assert client.post("/api/commands", json={}).status_code in (401, 503)


def test_retention_only_prunes_bus_history(tmp_path: Path) -> None:
    path = tmp_path / "retention.db"
    initialize_database(path)
    repository = ExternalDataRepository(path)
    repository.create(source="unrelated-existing-data", data={"keep": True})
    for number in range(5):
        repository.create(source="lta-bus-arrival:01219:225G", data={"number": number})
    repository.prune_bus_arrivals(keep=2)
    with open_connection(path) as connection:
        assert connection.execute("SELECT count(*) FROM external_api_snapshots").fetchone()[0] == 3
    assert repository.latest(source="unrelated-existing-data") is not None


def test_key_loaded_from_backend_environment_and_hidden(monkeypatch) -> None:
    monkeypatch.setenv("LTA_API_ACCOUNT_KEY", "private-test-key")
    get_settings.cache_clear()
    config = get_settings()
    assert config.lta_api_account_key == "private-test-key"
    assert "private-test-key" not in repr(config)
    get_settings.cache_clear()
