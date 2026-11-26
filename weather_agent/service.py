"""High-level weather snapshot shared by the agent tools, the dashboard and PDF reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import analysis, weather_api
from .pakistan import PAKISTAN_CITIES
from .weather_api import Location


@dataclass
class CitySnapshot:
    location: Location
    current: dict[str, Any]
    air: dict[str, Any]
    outlook: dict[str, Any]
    hourly: list[dict[str, Any]] = field(default_factory=list)
    air_hourly: list[dict[str, Any]] = field(default_factory=list)
    dust_storm_risk: str = "Low"
    daily: list[dict[str, Any]] = field(default_factory=list)
    source: str = "Open-Meteo"  # "MET Norway" when the backup source answered

    def to_dict(self, include_hourly: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "location": self.location.label,
            "data_source": self.source,
            "coordinates": [self.location.latitude, self.location.longitude],
            "timezone": self.location.timezone,
            "current": self.current,
            "air_quality": self.air,
            "outlook": self.outlook,
            "dust_storm_risk": self.dust_storm_risk,
        }
        if include_hourly:
            out["hourly"] = compact_hourly(self.hourly)
        return out


def compact_hourly(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Token-friendly per-hour view for the LLM."""
    out = []
    for r in rows:
        out.append({
            "time": r.get("time", "")[-5:] if r.get("time") else "",
            "date": r.get("time", "")[:10],
            "temp_c": r.get("temperature_2m"),
            "rh_pct": r.get("relative_humidity_2m"),
            "rain_prob_pct": r.get("precipitation_probability"),
            "precip_mm": r.get("precipitation"),
            "wx": analysis.describe_code(r.get("weather_code")),
            "wind_kmh": r.get("wind_speed_10m"),
            "gust_kmh": r.get("wind_gusts_10m"),
            "wind_dir": analysis.wind_compass(r.get("wind_direction_10m")),
            "cape": r.get("cape"),
            "storm_score": analysis.hour_storm_score(r),
        })
    return out


def get_snapshot(city: str, hours: int = 24, country_code: str | None = None) -> CitySnapshot:
    return get_snapshot_for(weather_api.geocode(city, country_code), hours)


def get_snapshot_for(loc: Location, hours: int = 24) -> CitySnapshot:
    """Snapshot for an already-resolved location (e.g. picked from search matches)."""
    forecast = weather_api.fetch_forecast(loc, hours)
    try:
        aq = weather_api.fetch_air_quality(loc, hours)
    except weather_api.WeatherAPIError:
        aq = {}
    rows = weather_api.hourly_rows(forecast)
    current = analysis.summarise_current(forecast.get("current") or {})
    air = analysis.summarise_air(aq)
    dust = analysis.dust_storm_risk(
        current.get("wind_speed_kmh"), current.get("wind_gusts_kmh"),
        current.get("humidity_pct"), air.get("pm10"), air.get("dust"),
    )
    return CitySnapshot(
        location=loc,
        current=current,
        air=air,
        outlook=analysis.analyse_hours(rows),
        hourly=rows,
        air_hourly=weather_api.hourly_rows(aq) if aq else [],
        dust_storm_risk=dust,
        daily=weather_api.daily_rows(forecast),
        source=forecast.get("source", "Open-Meteo"),
    )


def auto_summary(snap: CitySnapshot) -> str:
    """Rule-based Markdown summary (used for PDFs made without the LLM)."""
    c, a, o = snap.current, snap.air, snap.outlook
    lines = [
        f"## {snap.location.name}: {o.get('storm_risk', 'Unknown')} storm risk over the next {o.get('hours')} hours",
        f"Currently **{c.get('condition', 'n/a').lower()}**, {c.get('temperature_c')} C "
        f"(feels like {c.get('feels_like_c')} C), air humidity {c.get('humidity_pct')} %, "
        f"wind {c.get('wind_speed_kmh')} km/h from the {c.get('wind_direction')} "
        f"(gusts {c.get('wind_gusts_kmh')} km/h, Beaufort {c.get('beaufort')}).",
        "",
        "### Rain outlook",
    ]
    if o.get("rain_expected"):
        lines.append(
            f"- Rain expected from **{o.get('first_rain_time')}**, peak probability "
            f"{o.get('max_precip_probability_pct')} % at {o.get('max_precip_probability_time')}."
        )
        lines.append(f"- Total {o.get('total_precip_mm')} mm, peak intensity {o.get('peak_rain_intensity')}.")
    else:
        lines.append(f"- No significant rain expected (max probability {o.get('max_precip_probability_pct')} %).")
    lines += ["", "### Storm assessment"]
    th = o.get("thunderstorm_hours") or []
    lines.append(f"- Storm score {o.get('max_storm_score')}/100 (peak at {o.get('peak_storm_time')}).")
    lines.append(f"- Thunderstorm hours: {', '.join(h[-5:] for h in th) if th else 'none forecast'}.")
    lines.append(f"- Max gust {o.get('max_gust_kmh')} km/h; max CAPE {o.get('max_cape_jkg')} J/kg; "
                 f"pressure trend {o.get('pressure_trend_hpa')} hPa.")
    lines.append(f"- Dust-storm risk: {snap.dust_storm_risk}.")
    lines += ["", "### Air quality",
              f"- US AQI {a.get('us_aqi')} ({a.get('category')}); PM2.5 {a.get('pm2_5')}, PM10 {a.get('pm10')} ug/m3.",
              f"- {a.get('advice')}"]
    return "\n".join(lines)


def pakistan_outlook(hours: int = 12, cities: list[str] | None = None) -> list[dict[str, Any]]:
    """Rain/storm outlook for Pakistani cities, sorted by storm score (one API call)."""
    return pakistan_scan(hours, cities)[0]


def pakistan_scan(hours: int = 12, cities: list[str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (per-city summary sorted by storm score, city x hour matrix for heatmaps)."""
    names = cities or list(PAKISTAN_CITIES)
    locs = []
    for name in names:
        key = name.strip().title()
        if key in PAKISTAN_CITIES:
            lat, lon, prov = PAKISTAN_CITIES[key]
            locs.append(Location(key, lat, lon, "Pakistan", prov, "Asia/Karachi"))
    results = weather_api.fetch_forecast_many(locs, hours)
    table: list[dict[str, Any]] = []
    matrix: list[dict[str, Any]] = []
    for loc, fc in zip(locs, results):
        rows = weather_api.hourly_rows(fc)
        for r in rows:
            matrix.append({
                "city": loc.name,
                "time": r.get("time"),
                "rain_prob_pct": r.get("precipitation_probability"),
                "precip_mm": r.get("precipitation"),
                "storm_score": analysis.hour_storm_score(r),
                "gust_kmh": r.get("wind_gusts_10m"),
                "temp_c": r.get("temperature_2m"),
                "humidity_pct": r.get("relative_humidity_2m"),
                "condition": analysis.describe_code(r.get("weather_code")),
            })
        o = analysis.analyse_hours(rows)
        cur = analysis.summarise_current(fc.get("current") or {})
        table.append({
            "city": loc.name,
            "province": loc.admin1,
            "now": cur["condition"],
            "weather_code": (fc.get("current") or {}).get("weather_code"),
            "is_day": cur["is_day"],
            "temp_c": cur["temperature_c"],
            "humidity_pct": cur["humidity_pct"],
            "wind_kmh": cur["wind_speed_kmh"],
            "wind_dir": cur["wind_direction"],
            "storm_risk": o["storm_risk"],
            "storm_score": o["max_storm_score"],
            "rain_expected": o["rain_expected"],
            "first_rain": o["first_rain_time"],
            "max_rain_prob_pct": o["max_precip_probability_pct"],
            "total_precip_mm": o["total_precip_mm"],
            "max_gust_kmh": o["max_gust_kmh"],
            "thunderstorm_hours": len(o["thunderstorm_hours"]),
            "source": fc.get("source", "Open-Meteo"),
        })
    table.sort(key=lambda r: (r["storm_score"], r["max_rain_prob_pct"]), reverse=True)
    return table, matrix
