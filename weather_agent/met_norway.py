"""Backup forecast source: MET Norway Locationforecast 2.0 (free, no API key, worldwide).

Used only when Open-Meteo does not answer. The reply is converted into the same shape as an
Open-Meteo forecast (``current`` / ``hourly`` / ``daily`` column arrays, local times, km/h, WMO
weather codes) so the analysis, dashboard, agent tools and PDFs work unchanged. Fields MET does not
provide worldwide (gusts, rain probability, CAPE, lifted index, visibility, sunrise/sunset) are ``None``.

Data: MET Norway (api.met.no), licensed CC BY 4.0. Terms ask for an identifying User-Agent (set on the
shared session in ``weather_api``) and coordinates with at most 4 decimals.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import weather_api
from .weather_api import Location

URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
SOURCE = "MET Norway"
MS_TO_KMH = 3.6

_STATIC_CODES = {"clearsky": 0, "fair": 1, "partlycloudy": 2, "cloudy": 3, "fog": 45}


def symbol_to_wmo(symbol: str | None) -> int | None:
    """MET symbol code (e.g. ``heavyrainshowersandthunder_day``) -> nearest WMO weather code."""
    if not symbol:
        return None
    base = symbol.split("_", 1)[0]
    heavy, light = base.startswith("heavy"), base.startswith("light")
    if base in _STATIC_CODES:
        return _STATIC_CODES[base]
    if "thunder" in base:
        return 99 if heavy else 95
    if "sleet" in base:
        return 67 if heavy else 66
    if "snow" in base:
        if "showers" in base:
            return 86 if heavy else 85
        return 75 if heavy else 71 if light else 73
    if "rain" in base:
        if "showers" in base:
            return 82 if heavy else 80 if light else 81
        return 65 if heavy else 61 if light else 63
    return None


def _zone(loc: Location):
    try:
        return ZoneInfo(loc.timezone) if loc.timezone and loc.timezone != "auto" else timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def _kmh(ms: Any) -> float | None:
    return round(float(ms) * MS_TO_KMH, 1) if ms is not None else None


def _is_day(symbol: str | None, local: datetime) -> int:
    if symbol and symbol.endswith("_day"):
        return 1
    if symbol and ("_night" in symbol or "_polartwilight" in symbol):
        return 0
    return int(6 <= local.hour < 18)


def _hour_row(entry: dict[str, Any], tz) -> dict[str, Any]:
    local = datetime.fromisoformat(entry["time"].replace("Z", "+00:00")).astimezone(tz)
    inst = entry["data"]["instant"]["details"]
    nxt = entry["data"].get("next_1_hours") or {}
    det = nxt.get("details") or {}
    symbol = (nxt.get("summary") or {}).get("symbol_code")
    precip = det.get("precipitation_amount")
    return {
        "time": local.strftime("%Y-%m-%dT%H:%M"),
        "temperature_2m": inst.get("air_temperature"),
        "apparent_temperature": inst.get("apparent_air_temperature", inst.get("air_temperature")),
        "relative_humidity_2m": inst.get("relative_humidity"),
        "dew_point_2m": inst.get("dew_point_temperature"),
        "precipitation_probability": det.get("probability_of_precipitation"),
        "precipitation": precip,
        "rain": precip,
        "showers": None,
        "weather_code": symbol_to_wmo(symbol),
        "cloud_cover": inst.get("cloud_area_fraction"),
        "pressure_msl": inst.get("air_pressure_at_sea_level"),
        "visibility": None,
        "wind_speed_10m": _kmh(inst.get("wind_speed")),
        "wind_direction_10m": inst.get("wind_from_direction"),
        "wind_gusts_10m": _kmh(inst.get("wind_speed_of_gust")),
        "cape": None,
        "lifted_index": None,
        "is_day": _is_day(symbol, local),
    }


def _daily(series: list[dict[str, Any]], tz, days: int) -> dict[str, list[Any]]:
    """Per local day: high/low, rain total, strongest wind, most significant weather, UV."""
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in series:
        local = datetime.fromisoformat(entry["time"].replace("Z", "+00:00")).astimezone(tz)
        by_day[local.date().isoformat()].append(entry)
    out: dict[str, list[Any]] = defaultdict(list)
    for day in sorted(by_day)[:days]:
        temps, rain, winds, codes, uvs, probs, gusts = [], 0.0, [], [], [], [], []
        for e in by_day[day]:
            inst, data = e["data"]["instant"]["details"], e["data"]
            block = data.get("next_1_hours") or data.get("next_6_hours") or {}
            det = block.get("details") or {}
            temps += [t for t in (inst.get("air_temperature"), det.get("air_temperature_max"),
                                  det.get("air_temperature_min")) if t is not None]
            rain += det.get("precipitation_amount") or 0.0
            if det.get("probability_of_precipitation") is not None:
                probs.append(det["probability_of_precipitation"])
            if inst.get("wind_speed") is not None:
                winds.append((inst["wind_speed"], inst.get("wind_from_direction")))
            if inst.get("wind_speed_of_gust") is not None:
                gusts.append(inst["wind_speed_of_gust"])
            if inst.get("ultraviolet_index_clear_sky") is not None:
                uvs.append(inst["ultraviolet_index_clear_sky"])
            code = symbol_to_wmo((block.get("summary") or {}).get("symbol_code"))
            if code is not None:
                codes.append(code)
        top_wind = max(winds, default=(None, None))
        out["time"].append(day)
        out["weather_code"].append(max(codes) if codes else None)
        out["temperature_2m_max"].append(max(temps) if temps else None)
        out["temperature_2m_min"].append(min(temps) if temps else None)
        out["precipitation_sum"].append(round(rain, 1))
        out["precipitation_probability_max"].append(max(probs) if probs else None)
        out["wind_speed_10m_max"].append(_kmh(top_wind[0]))
        out["wind_gusts_10m_max"].append(_kmh(max(gusts)) if gusts else None)
        out["wind_direction_10m_dominant"].append(top_wind[1])
        out["sunrise"].append(None)
        out["sunset"].append(None)
        out["uv_index_max"].append(max(uvs) if uvs else None)
    return dict(out)


def to_open_meteo(raw: dict[str, Any], loc: Location, hours: int, days: int = weather_api.FORECAST_DAYS) -> dict[str, Any]:
    """Convert a MET Norway reply into the Open-Meteo forecast shape used across the app."""
    tz = _zone(loc)
    series = (raw.get("properties") or {}).get("timeseries") or []
    if not series:
        raise weather_api.WeatherAPIError(f"{SOURCE} returned no forecast data.")
    hourly_rows = [_hour_row(e, tz) for e in series if e["data"].get("next_1_hours")][:hours]
    columns = [k for k in hourly_rows[0] if k != "apparent_temperature"] if hourly_rows else ["time"]
    hourly = {k: [r[k] for r in hourly_rows] for k in columns}
    now = _hour_row(series[0], tz)
    current = {k: now[k] for k in ("time", "temperature_2m", "relative_humidity_2m", "apparent_temperature",
                                   "is_day", "precipitation", "rain", "weather_code", "cloud_cover",
                                   "pressure_msl", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m")}
    return {"latitude": loc.latitude, "longitude": loc.longitude, "timezone": str(tz), "source": SOURCE,
            "current": current, "hourly": hourly, "daily": _daily(series, tz, days)}


def fetch_forecast(loc: Location, hours: int = 24) -> dict[str, Any]:
    hours = max(1, min(int(hours), weather_api.MAX_FORECAST_HOURS))
    raw = weather_api.get_json(URL, {"lat": round(loc.latitude, 4), "lon": round(loc.longitude, 4)})
    return to_open_meteo(raw, loc, hours)


def fetch_forecast_many(locs: list[Location], hours: int = 12) -> list[dict[str, Any]]:
    """One MET request per location (no multi-location endpoint); a few in parallel, well inside MET's limits."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda loc: fetch_forecast(loc, hours), locs))
