from unittest.mock import MagicMock

import pytest
import requests

from weather_agent import weather_api

MET_SAMPLE = {"properties": {"timeseries": [
    {"time": "2026-11-26T04:00:00Z", "data": {
        "instant": {"details": {"air_temperature": 17.3, "relative_humidity": 73.2, "wind_speed": 10.0,
                                "wind_from_direction": 270.0, "air_pressure_at_sea_level": 1018.4,
                                "cloud_area_fraction": 0.0, "ultraviolet_index_clear_sky": 1.3}},
        "next_1_hours": {"summary": {"symbol_code": "clearsky_day"}, "details": {"precipitation_amount": 0.0}}}},
    {"time": "2026-11-26T05:00:00Z", "data": {
        "instant": {"details": {"air_temperature": 18.0, "relative_humidity": 70.0, "wind_speed": 5.0,
                                "wind_from_direction": 90.0}},
        "next_1_hours": {"summary": {"symbol_code": "heavyrainshowersandthunder_day"},
                         "details": {"precipitation_amount": 4.2}}}},
    {"time": "2026-11-26T18:00:00Z", "data": {
        "instant": {"details": {"air_temperature": 12.0, "relative_humidity": 90.0, "wind_speed": 2.0,
                                "wind_from_direction": 0.0}},
        "next_6_hours": {"summary": {"symbol_code": "rain"},
                         "details": {"precipitation_amount": 3.0, "air_temperature_min": 10.5}}}},
]}}


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


def _calls_to(get, host: str) -> int:
    return sum(host in c.args[0] for c in get.call_args_list)


def test_timeout_is_retried_then_succeeds(monkeypatch):
    get = MagicMock(side_effect=[requests.ReadTimeout("slow"), _resp(200, {"hourly": {}})])
    monkeypatch.setattr(weather_api._session, "get", get)
    assert weather_api.fetch_forecast(weather_api.Location("X", 0, 0, "Y")) == {"hourly": {}}
    assert get.call_count == weather_api.ATTEMPTS == 2


def test_timeout_after_all_attempts_gives_friendly_message(monkeypatch):
    get = MagicMock(side_effect=requests.ReadTimeout("HTTPSConnectionPool(...): Read timed out."))
    monkeypatch.setattr(weather_api._session, "get", get)
    with pytest.raises(weather_api.WeatherAPIError) as err:
        weather_api.fetch_forecast(weather_api.Location("X", 0, 0, "Y"))
    msg = str(err.value)
    assert "did not answer in time" in msg and "MET Norway" in msg and "HTTPSConnectionPool" not in msg
    assert _calls_to(get, "open-meteo") == weather_api.ATTEMPTS  # then the backup was tried too
    assert _calls_to(get, "api.met.no") == weather_api.ATTEMPTS


def test_client_errors_are_not_retried(monkeypatch):
    get = MagicMock(return_value=_resp(400, {"reason": "bad"}))
    monkeypatch.setattr(weather_api._session, "get", get)
    with pytest.raises(weather_api.WeatherAPIError):
        weather_api.fetch_forecast(weather_api.Location("X", 0, 0, "Y"))
    assert _calls_to(get, "open-meteo") == 1


def test_backup_source_answers_when_open_meteo_is_down(monkeypatch):
    def fake(url, **kw):
        if "open-meteo" in url:
            raise requests.ConnectTimeout("down")
        return _resp(200, MET_SAMPLE)

    get = MagicMock(side_effect=fake)
    monkeypatch.setattr(weather_api._session, "get", get)
    loc = weather_api.Location("Lahore", 31.55, 74.34, "Pakistan", "Punjab", "Asia/Karachi")
    fc = weather_api.fetch_forecast(loc, 24)
    assert fc["source"] == "MET Norway" and fc["current"]["temperature_2m"] == 17.3
    assert weather_api.fetch_forecast_many([loc, loc], 6)[1]["source"] == "MET Norway"


def test_circuit_breaker_skips_a_down_service_for_a_while(monkeypatch):
    clock = [5000.0]
    monkeypatch.setattr(weather_api.time, "monotonic", lambda: clock[0])
    get = MagicMock(side_effect=requests.ConnectTimeout("down"))
    monkeypatch.setattr(weather_api._session, "get", get)
    loc = weather_api.Location("X", 1, 2, "Y")
    with pytest.raises(weather_api.WeatherAPIError):
        weather_api.fetch_forecast(loc)
    calls = get.call_count
    assert weather_api.is_down("Open-Meteo")  # header status light turns red
    with pytest.raises(weather_api.WeatherAPIError, match="not responding right now"):
        weather_api.fetch_air_quality(loc)  # other Open-Meteo servers are skipped too: fails instantly
    assert get.call_count == calls
    clock[0] += weather_api.BREAKER_S + 1
    assert not weather_api.is_down("Open-Meteo")
    with pytest.raises(weather_api.WeatherAPIError, match="did not answer"):
        weather_api.fetch_air_quality(loc)  # after the pause it is tried again
    assert get.call_count == calls + weather_api.ATTEMPTS


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


@pytest.mark.parametrize("symbol,code", [
    ("clearsky_night", 0), ("fair_day", 1), ("partlycloudy_day", 2), ("cloudy", 3), ("fog", 45),
    ("lightrain", 61), ("rain", 63), ("heavyrain", 65), ("lightrainshowers_day", 80), ("rainshowers_night", 81),
    ("heavyrainshowers_day", 82), ("rainandthunder", 95), ("heavyrainshowersandthunder_day", 99),
    ("snow", 73), ("heavysnowshowers_day", 86), ("sleet", 66), (None, None),
])
def test_met_symbols_map_to_wmo_codes(symbol, code):
    from weather_agent import met_norway

    assert met_norway.symbol_to_wmo(symbol) == code


def test_met_reply_converted_to_open_meteo_shape():
    from weather_agent import met_norway

    loc = weather_api.Location("Lahore", 31.55, 74.34, "Pakistan", "Punjab", "Asia/Karachi")
    fc = met_norway.to_open_meteo(MET_SAMPLE, loc, 24)
    rows = weather_api.hourly_rows(fc)
    assert [r["time"] for r in rows] == ["2026-11-26T09:00", "2026-11-26T10:00"]  # UTC -> Pakistan time
    assert rows[0]["wind_speed_10m"] == 36.0 and rows[1]["weather_code"] == 99 and rows[1]["precipitation"] == 4.2
    assert rows[0]["wind_gusts_10m"] is None and rows[0]["cape"] is None  # not provided outside Scandinavia
    assert fc["current"]["is_day"] == 1 and fc["current"]["apparent_temperature"] == 17.3
    days = weather_api.daily_rows(fc)
    assert [d["date"] for d in days] == ["2026-11-26"]  # 18:00 UTC is still the 26th in Pakistan
    day = days[0]
    assert day["temperature_2m_max"] == 18.0 and day["temperature_2m_min"] == 10.5  # incl. 6-hour block minimum
    assert day["precipitation_sum"] == 7.2  # hourly amounts + the 6-hour block
    assert day["weather_code"] == 99 and day["uv_index_max"] == 1.3 and day["sunrise"] is None
