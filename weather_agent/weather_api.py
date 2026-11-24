"""Open-Meteo client (free, no API key).

Endpoints used:
- Geocoding:   https://geocoding-api.open-meteo.com/v1/search
- Forecast:    https://api.open-meteo.com/v1/forecast
- Air quality: https://air-quality-api.open-meteo.com/v1/air-quality

Weather data by Open-Meteo.com, licensed CC BY 4.0. Free for non-commercial use.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from .pakistan import PAKISTAN_CITIES

log = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

TIMEOUT_S = (5, 10)  # (connect, read) seconds per attempt; a healthy reply takes well under 1 s
ATTEMPTS = 3  # shared cloud hosts (Streamlit Cloud) see occasional slow replies / 429s: retry briefly
RETRY_BACKOFF_S = 0.6  # wait 0.6 s, then 1.2 s between attempts
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
CACHE_TTL_S = 600  # weather models update hourly; 10 min keeps data "live" but saves calls
STALE_MAX_S = 6 * 3600  # if the service is down, serve the last good answer up to 6 h old
MAX_FORECAST_HOURS = 72

CURRENT_VARS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,"
    "weather_code,cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
)
HOURLY_VARS = (
    "temperature_2m,relative_humidity_2m,dew_point_2m,precipitation_probability,precipitation,"
    "rain,showers,weather_code,cloud_cover,pressure_msl,visibility,wind_speed_10m,"
    "wind_direction_10m,wind_gusts_10m,cape,lifted_index,is_day"
)
DAILY_VARS = (
    "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,"
    "wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,sunrise,sunset,uv_index_max"
)
FORECAST_DAYS = 7
AQ_CURRENT_VARS = "us_aqi,european_aqi,pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,dust"
AQ_HOURLY_VARS = "us_aqi,pm10,pm2_5,dust"


class WeatherAPIError(RuntimeError):
    """Raised when Open-Meteo cannot answer a request."""


@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float
    country: str
    admin1: str = ""
    timezone: str = "auto"

    @property
    def label(self) -> str:
        parts = [self.name, self.admin1, self.country]
        return ", ".join(p for p in parts if p)


_cache: dict[tuple, tuple[float, Any]] = {}
_cache_lock = threading.Lock()
_session = requests.Session()
_session.headers.update({"User-Agent": "weather-storm-agent/1.0"})


def _source(url: str) -> str:
    host = urlparse(url).hostname or url
    return "Open-Meteo" if "open-meteo" in host else host


def _fetch(url: str, params: dict[str, Any]) -> Any:
    """One GET with short retries on timeouts, dropped connections, 429 and 5xx."""
    source = _source(url)
    for attempt in range(1, ATTEMPTS + 1):
        last = attempt == ATTEMPTS
        try:
            resp = _session.get(url, params=params, timeout=TIMEOUT_S)
        except requests.Timeout as exc:
            if last:
                raise WeatherAPIError(f"Network error: {source} did not answer in time (tried {ATTEMPTS}×). "
                                      "The free service may be busy; please try again in a moment.") from exc
        except requests.RequestException as exc:
            if last:
                raise WeatherAPIError(f"Network error: could not reach {source} (tried {ATTEMPTS}×). "
                                      "Please try again in a moment.") from exc
        else:
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code not in RETRY_STATUSES or last:
                reason = ""
                try:
                    reason = resp.json().get("reason", "")
                except (ValueError, AttributeError):
                    pass
                raise WeatherAPIError(f"{source} returned HTTP {resp.status_code} {reason}".strip())
        log.warning("%s request failed (attempt %d/%d), retrying", source, attempt, ATTEMPTS)
        time.sleep(RETRY_BACKOFF_S * attempt)
    raise AssertionError("unreachable")  # pragma: no cover


def _get(url: str, params: dict[str, Any]) -> Any:
    key = (url, tuple(sorted(params.items())))
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_S:
            return hit[1]
    try:
        data = _fetch(url, params)
    except WeatherAPIError:
        if hit and now - hit[0] < STALE_MAX_S:  # service hiccup: keep showing the last good answer
            log.warning("%s unavailable; serving cached data %.0f s old", _source(url), now - hit[0])
            return hit[1]
        raise
    with _cache_lock:
        for k in [k for k, (t, _) in _cache.items() if now - t >= STALE_MAX_S]:
            del _cache[k]  # keep the cache bounded
        _cache[key] = (now, data)
    return data


def get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """Cached GET for other free data sources (e.g. USGS earthquakes)."""
    return _get(url, params)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def search_cities(query: str, count: int = 8, country_code: str | None = None) -> list[Location]:
    """All geocoding matches for a name (for "did you mean" pickers), best match first."""
    name = query.strip()
    if len(name) < 2:
        return []
    params: dict[str, Any] = {"name": name, "count": max(1, min(count, 20)), "language": "en", "format": "json"}
    if country_code:
        params["countryCode"] = country_code.upper()
    data = _get(GEOCODING_URL, params)
    return [
        Location(
            name=r["name"],
            latitude=float(r["latitude"]),
            longitude=float(r["longitude"]),
            country=r.get("country", ""),
            admin1=r.get("admin1", ""),
            timezone=r.get("timezone", "auto"),
        )
        for r in data.get("results") or []
    ]


def geocode(city: str, country_code: str | None = None) -> Location:
    """Resolve a city name to coordinates. Pakistani cities resolve offline first."""
    name = city.strip()
    if not name:
        raise WeatherAPIError("City name is empty.")
    known = PAKISTAN_CITIES.get(name.title())
    if known and country_code in (None, "PK"):
        return Location(name.title(), known[0], known[1], "Pakistan", known[2], "Asia/Karachi")
    matches = search_cities(name, 1, country_code)
    if not matches:
        raise WeatherAPIError(f"Could not find a city named '{city}'.")
    return matches[0]


def fetch_forecast(loc: Location, hours: int = 24) -> dict[str, Any]:
    """Current conditions + hourly forecast for the next ``hours`` hours."""
    hours = max(1, min(int(hours), MAX_FORECAST_HOURS))
    params = {
        "latitude": round(loc.latitude, 4),
        "longitude": round(loc.longitude, 4),
        "current": CURRENT_VARS,
        "hourly": HOURLY_VARS,
        "daily": DAILY_VARS,
        "forecast_hours": hours,
        "forecast_days": FORECAST_DAYS,
        "timezone": loc.timezone or "auto",
        "wind_speed_unit": "kmh",
    }
    return _get(FORECAST_URL, params)


def daily_rows(forecast: dict[str, Any]) -> list[dict[str, Any]]:
    """Open-Meteo daily column arrays -> list of per-day dicts."""
    daily = forecast.get("daily") or {}
    days = daily.get("time") or []
    return [{"date": d, **{k: v[i] for k, v in daily.items() if k != "time" and i < len(v)}}
            for i, d in enumerate(days)]


def fetch_air_quality(loc: Location, hours: int = 24) -> dict[str, Any]:
    hours = max(1, min(int(hours), MAX_FORECAST_HOURS))
    params = {
        "latitude": round(loc.latitude, 4),
        "longitude": round(loc.longitude, 4),
        "current": AQ_CURRENT_VARS,
        "hourly": AQ_HOURLY_VARS,
        "forecast_hours": hours,
        "timezone": loc.timezone or "auto",
    }
    return _get(AIR_QUALITY_URL, params)


def fetch_forecast_many(locs: list[Location], hours: int = 12) -> list[dict[str, Any]]:
    """Hourly forecast for several locations in ONE request (Open-Meteo multi-location)."""
    if not locs:
        return []
    hours = max(1, min(int(hours), MAX_FORECAST_HOURS))
    params = {
        "latitude": ",".join(f"{loc.latitude:.4f}" for loc in locs),
        "longitude": ",".join(f"{loc.longitude:.4f}" for loc in locs),
        "current": CURRENT_VARS,
        "hourly": HOURLY_VARS,
        "forecast_hours": hours,
        "timezone": locs[0].timezone or "auto",
        "wind_speed_unit": "kmh",
    }
    data = _get(FORECAST_URL, params)
    return data if isinstance(data, list) else [data]


def hourly_rows(forecast: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn Open-Meteo's column arrays into a list of per-hour dicts."""
    hourly = forecast.get("hourly") or {}
    times = hourly.get("time") or []
    rows = []
    for i, t in enumerate(times):
        row = {"time": t}
        for key, values in hourly.items():
            if key != "time" and i < len(values):
                row[key] = values[i]
        rows.append(row)
    return rows
