"""Deterministic meteorological reasoning base.

The LLM never invents numbers: tools compute these indicators from live
Open-Meteo data and the agent explains them. Thresholds follow common
forecasting practice:

- WMO weather codes 95/96/99 = thunderstorm (with hail for 96/99).
- CAPE (J/kg): <300 weak, 300-1000 moderate, 1000-2500 strong, >2500 extreme instability.
- Lifted index: >0 stable, 0..-3 marginal, -3..-6 unstable, < -6 very unstable.
- Gusts (km/h): >=50 strong, >=62 gale (Beaufort 8), >=89 storm (Beaufort 10).
- Rain rate (mm/h): <2.5 light, 2.5-7.6 moderate, 7.6-50 heavy, >50 violent.
- US AQI bands from the US EPA.
"""

from __future__ import annotations

from typing import Any

WMO_CODES: dict[int, str] = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}
THUNDER_CODES = {95, 96, 99}
RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82} | THUNDER_CODES

COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def describe_code(code: Any) -> str:
    try:
        return WMO_CODES.get(int(code), f"Unknown ({code})")
    except (TypeError, ValueError):
        return "Unknown"


def wind_compass(degrees: Any) -> str:
    try:
        return COMPASS[int((float(degrees) % 360) / 22.5 + 0.5) % 16]
    except (TypeError, ValueError):
        return "n/a"


def beaufort(speed_kmh: Any) -> tuple[int, str]:
    limits = [(1, "Calm"), (6, "Light air"), (12, "Light breeze"), (20, "Gentle breeze"),
              (29, "Moderate breeze"), (39, "Fresh breeze"), (50, "Strong breeze"),
              (62, "Near gale"), (75, "Gale"), (89, "Strong gale"), (103, "Storm"),
              (118, "Violent storm")]
    s = _num(speed_kmh)
    for force, (limit, name) in enumerate(limits):
        if s < limit:
            return force, name
    return 12, "Hurricane force"


def aqi_category(us_aqi: Any) -> str:
    a = _num(us_aqi, default=-1)
    if a < 0:
        return "Unknown"
    for limit, name in ((50, "Good"), (100, "Moderate"), (150, "Unhealthy for sensitive groups"),
                        (200, "Unhealthy"), (300, "Very unhealthy")):
        if a <= limit:
            return name
    return "Hazardous"


def aqi_advice(us_aqi: Any) -> str:
    cat = aqi_category(us_aqi)
    return {
        "Good": "Air quality is satisfactory; no precautions needed.",
        "Moderate": "Acceptable; unusually sensitive people should limit prolonged outdoor exertion.",
        "Unhealthy for sensitive groups": "Children, elderly and people with asthma/heart disease should reduce outdoor activity.",
        "Unhealthy": "Everyone should reduce prolonged outdoor exertion; sensitive groups avoid it. Masks advised.",
        "Very unhealthy": "Health alert: avoid outdoor activity, keep windows closed, use N95 masks.",
        "Hazardous": "Emergency conditions: stay indoors, use air purifiers if available.",
    }.get(cat, "No air-quality data available.")


def rain_intensity(mm_per_h: Any) -> str:
    r = _num(mm_per_h)
    if r <= 0:
        return "none"
    if r < 2.5:
        return "light"
    if r < 7.6:
        return "moderate"
    if r < 50:
        return "heavy"
    return "violent"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def hour_storm_score(row: dict[str, Any]) -> int:
    """0-100 storm likelihood/severity score for one forecast hour."""
    score = 0.0
    code = int(_num(row.get("weather_code"), -1))
    cape = _num(row.get("cape"))
    li = _num(row.get("lifted_index"), 10.0)
    gust = _num(row.get("wind_gusts_10m"))
    pop = _num(row.get("precipitation_probability"))
    precip = _num(row.get("precipitation"))

    if code in THUNDER_CODES:
        score += 45 + (10 if code in (96, 99) else 0)
    elif code in (65, 67, 82):
        score += 20

    if cape >= 2500:
        score += 25
    elif cape >= 1000:
        score += 18
    elif cape >= 300:
        score += 8

    if li < -6:
        score += 15
    elif li < -3:
        score += 10
    elif li < 0:
        score += 4

    if gust >= 89:
        score += 25
    elif gust >= 62:
        score += 18
    elif gust >= 50:
        score += 10

    # convection needs moisture: weight by rain probability
    score += 10 * (pop / 100.0)
    if precip >= 7.6:
        score += 10
    return int(min(100, round(score)))


def risk_level(score: int) -> str:
    if score >= 70:
        return "Severe"
    if score >= 45:
        return "High"
    if score >= 20:
        return "Moderate"
    return "Low"


def dust_storm_risk(current_wind_kmh: Any, gust_kmh: Any, humidity: Any, pm10: Any, dust: Any) -> str:
    """Heuristic for dust/sand storms (common in Sindh, Balochistan and south Punjab)."""
    wind = max(_num(current_wind_kmh), _num(gust_kmh))
    hum = _num(humidity, 100)
    p10 = _num(pm10)
    dst = _num(dust)
    if wind >= 50 and hum < 35 and (p10 >= 250 or dst >= 150):
        return "High"
    if wind >= 35 and hum < 40 and (p10 >= 150 or dst >= 80):
        return "Moderate"
    return "Low"


def analyse_hours(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise rain and storm outlook over a list of hourly rows."""
    if not rows:
        return {"hours": 0, "storm_risk": "Unknown", "max_storm_score": 0}

    scores = [hour_storm_score(r) for r in rows]
    peak_i = max(range(len(scores)), key=scores.__getitem__)
    rain_hours = [r for r in rows
                  if _num(r.get("precipitation_probability")) >= 50
                  or _num(r.get("precipitation")) >= 0.2
                  or int(_num(r.get("weather_code"), -1)) in RAIN_CODES]
    thunder_hours = [r["time"] for r in rows if int(_num(r.get("weather_code"), -1)) in THUNDER_CODES]
    max_pop_row = max(rows, key=lambda r: _num(r.get("precipitation_probability")))
    max_gust_row = max(rows, key=lambda r: _num(r.get("wind_gusts_10m")))
    total_precip = round(sum(_num(r.get("precipitation")) for r in rows), 1)
    max_rate = max(_num(r.get("precipitation")) for r in rows)

    return {
        "hours": len(rows),
        "from": rows[0]["time"],
        "to": rows[-1]["time"],
        "storm_risk": risk_level(scores[peak_i]),
        "max_storm_score": scores[peak_i],
        "peak_storm_time": rows[peak_i]["time"],
        "thunderstorm_hours": thunder_hours,
        "rain_expected": bool(rain_hours),
        "first_rain_time": rain_hours[0]["time"] if rain_hours else None,
        "rain_hour_count": len(rain_hours),
        "max_precip_probability_pct": _num(max_pop_row.get("precipitation_probability")),
        "max_precip_probability_time": max_pop_row["time"],
        "total_precip_mm": total_precip,
        "peak_rain_intensity": rain_intensity(max_rate),
        "max_gust_kmh": _num(max_gust_row.get("wind_gusts_10m")),
        "max_gust_time": max_gust_row["time"],
        "max_cape_jkg": max(_num(r.get("cape")) for r in rows),
        "min_lifted_index": min(_num(r.get("lifted_index"), 10.0) for r in rows),
        "pressure_trend_hpa": round(_num(rows[-1].get("pressure_msl")) - _num(rows[0].get("pressure_msl")), 1),
    }


def summarise_current(current: dict[str, Any]) -> dict[str, Any]:
    force, force_name = beaufort(current.get("wind_speed_10m"))
    return {
        "time": current.get("time"),
        "condition": describe_code(current.get("weather_code")),
        "weather_code": current.get("weather_code"),
        "temperature_c": current.get("temperature_2m"),
        "feels_like_c": current.get("apparent_temperature"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "wind_gusts_kmh": current.get("wind_gusts_10m"),
        "wind_direction_deg": current.get("wind_direction_10m"),
        "wind_direction": wind_compass(current.get("wind_direction_10m")),
        "beaufort": f"{force} ({force_name})",
        "pressure_hpa": current.get("pressure_msl"),
        "cloud_cover_pct": current.get("cloud_cover"),
        "precipitation_mm": current.get("precipitation"),
        "is_day": bool(current.get("is_day")),
    }


def summarise_air(aq: dict[str, Any]) -> dict[str, Any]:
    cur = aq.get("current") or {}
    us = cur.get("us_aqi")
    return {
        "time": cur.get("time"),
        "us_aqi": us,
        "category": aqi_category(us),
        "advice": aqi_advice(us),
        "european_aqi": cur.get("european_aqi"),
        "pm2_5": cur.get("pm2_5"),
        "pm10": cur.get("pm10"),
        "dust": cur.get("dust"),
        "ozone": cur.get("ozone"),
        "nitrogen_dioxide": cur.get("nitrogen_dioxide"),
        "sulphur_dioxide": cur.get("sulphur_dioxide"),
        "carbon_monoxide": cur.get("carbon_monoxide"),
    }
