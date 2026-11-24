from unittest.mock import MagicMock

import pytest
import requests

from weather_agent import weather_api


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    monkeypatch.setattr(weather_api, "RETRY_BACKOFF_S", 0)  # no real waiting between retries in tests
    weather_api.clear_cache()
    yield
    weather_api.clear_cache()


def _resp(status: int, payload):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    return r


def test_pakistani_city_resolves_offline(monkeypatch):
    get = MagicMock()
    monkeypatch.setattr(weather_api._session, "get", get)
    loc = weather_api.geocode("karachi")
    assert loc.name == "Karachi" and loc.country == "Pakistan" and loc.timezone == "Asia/Karachi"
    get.assert_not_called()


def test_geocode_world_city(monkeypatch):
    payload = {"results": [{"name": "Tokyo", "latitude": 35.68, "longitude": 139.69,
                            "country": "Japan", "admin1": "Tokyo", "timezone": "Asia/Tokyo"}]}
    monkeypatch.setattr(weather_api._session, "get", MagicMock(return_value=_resp(200, payload)))
    loc = weather_api.geocode("Tokyo")
    assert loc.label == "Tokyo, Tokyo, Japan" and loc.timezone == "Asia/Tokyo"


def test_geocode_not_found(monkeypatch):
    monkeypatch.setattr(weather_api._session, "get", MagicMock(return_value=_resp(200, {})))
    with pytest.raises(weather_api.WeatherAPIError, match="Could not find"):
        weather_api.geocode("Atlantis-on-Mars")


def test_http_error_raises(monkeypatch):
    monkeypatch.setattr(weather_api._session, "get",
                        MagicMock(return_value=_resp(400, {"reason": "bad latitude"})))
    loc = weather_api.Location("X", 0, 0, "Y")
    with pytest.raises(weather_api.WeatherAPIError, match="HTTP 400 bad latitude"):
        weather_api.fetch_forecast(loc)


def test_network_error_raises(monkeypatch):
    monkeypatch.setattr(weather_api._session, "get", MagicMock(side_effect=requests.ConnectionError("down")))
    with pytest.raises(weather_api.WeatherAPIError, match="Network error"):
        weather_api.fetch_forecast(weather_api.Location("X", 0, 0, "Y"))


def test_timeout_is_retried_then_succeeds(monkeypatch):
    get = MagicMock(side_effect=[requests.ReadTimeout("slow"), _resp(503, {}), _resp(200, {"hourly": {}})])
    monkeypatch.setattr(weather_api._session, "get", get)
    assert weather_api.fetch_forecast(weather_api.Location("X", 0, 0, "Y")) == {"hourly": {}}
    assert get.call_count == weather_api.ATTEMPTS


def test_timeout_after_all_attempts_gives_friendly_message(monkeypatch):
    get = MagicMock(side_effect=requests.ReadTimeout("HTTPSConnectionPool(...): Read timed out."))
    monkeypatch.setattr(weather_api._session, "get", get)
    with pytest.raises(weather_api.WeatherAPIError) as err:
        weather_api.fetch_forecast(weather_api.Location("X", 0, 0, "Y"))
    assert "did not answer in time" in str(err.value) and "HTTPSConnectionPool" not in str(err.value)
    assert get.call_count == weather_api.ATTEMPTS


def test_client_errors_are_not_retried(monkeypatch):
    get = MagicMock(return_value=_resp(400, {"reason": "bad"}))
    monkeypatch.setattr(weather_api._session, "get", get)
    with pytest.raises(weather_api.WeatherAPIError):
        weather_api.fetch_forecast(weather_api.Location("X", 0, 0, "Y"))
    assert get.call_count == 1


def test_stale_cache_served_when_service_is_down(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(weather_api.time, "monotonic", lambda: clock[0])
    loc = weather_api.Location("X", 1, 2, "Y")
    monkeypatch.setattr(weather_api._session, "get", MagicMock(return_value=_resp(200, {"hourly": {"time": []}})))
    weather_api.fetch_forecast(loc, 6)
    clock[0] += weather_api.CACHE_TTL_S + 1  # expired, but still within the stale window
    monkeypatch.setattr(weather_api._session, "get", MagicMock(side_effect=requests.ConnectionError("down")))
    assert weather_api.fetch_forecast(loc, 6) == {"hourly": {"time": []}}
    clock[0] += weather_api.STALE_MAX_S  # too old now: the error surfaces
    with pytest.raises(weather_api.WeatherAPIError, match="Network error"):
        weather_api.fetch_forecast(loc, 6)


def test_usgs_errors_name_the_right_service(monkeypatch):
    monkeypatch.setattr(weather_api._session, "get", MagicMock(return_value=_resp(400, {})))
    with pytest.raises(weather_api.WeatherAPIError, match="earthquake.usgs.gov returned HTTP 400"):
        weather_api.get_json("https://earthquake.usgs.gov/fdsnws/event/1/query", {})


def test_responses_are_cached(monkeypatch):
    get = MagicMock(return_value=_resp(200, {"hourly": {}}))
    monkeypatch.setattr(weather_api._session, "get", get)
    loc = weather_api.Location("X", 1, 2, "Y")
    weather_api.fetch_forecast(loc, 6)
    weather_api.fetch_forecast(loc, 6)
    assert get.call_count == 1


def test_forecast_hours_clamped(monkeypatch):
    get = MagicMock(return_value=_resp(200, {}))
    monkeypatch.setattr(weather_api._session, "get", get)
    weather_api.fetch_forecast(weather_api.Location("X", 1, 2, "Y"), 500)
    assert get.call_args.kwargs["params"]["forecast_hours"] == weather_api.MAX_FORECAST_HOURS


def test_hourly_rows():
    fc = {"hourly": {"time": ["t0", "t1"], "temperature_2m": [1.0, 2.0], "cape": [0, 10]}}
    assert weather_api.hourly_rows(fc) == [
        {"time": "t0", "temperature_2m": 1.0, "cape": 0},
        {"time": "t1", "temperature_2m": 2.0, "cape": 10},
    ]
