import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["LANGSMITH_TRACING"] = "false"

from weather_agent import analysis  # noqa: E402
from weather_agent.service import CitySnapshot  # noqa: E402
from weather_agent.weather_api import Location  # noqa: E402


def make_rows(n: int = 6, storm_at: int | None = 3) -> list[dict]:
    rows = []
    for i in range(n):
        storm = storm_at is not None and i == storm_at
        rows.append({
            "time": f"2026-07-15T{12 + i:02d}:00",
            "temperature_2m": 34.0 - i,
            "relative_humidity_2m": 60 + i,
            "dew_point_2m": 25.0,
            "precipitation_probability": 85 if storm else 10,
            "precipitation": 12.0 if storm else 0.0,
            "rain": 12.0 if storm else 0.0,
            "showers": 0.0,
            "weather_code": 95 if storm else 1,
            "cloud_cover": 90 if storm else 20,
            "pressure_msl": 1004.0 - i,
            "visibility": 10000,
            "wind_speed_10m": 20.0,
            "wind_direction_10m": 225,
            "wind_gusts_10m": 75.0 if storm else 25.0,
            "cape": 2200.0 if storm else 150.0,
            "lifted_index": -5.0 if storm else 2.0,
        })
    return rows


@pytest.fixture
def snapshot() -> CitySnapshot:
    rows = make_rows()
    current = analysis.summarise_current({
        "time": "2026-07-15T12:00", "temperature_2m": 34.0, "relative_humidity_2m": 60,
        "apparent_temperature": 39.0, "is_day": 1, "precipitation": 0.0, "weather_code": 2,
        "cloud_cover": 30, "pressure_msl": 1004.0, "wind_speed_10m": 20.0,
        "wind_direction_10m": 225, "wind_gusts_10m": 30.0,
    })
    air = analysis.summarise_air({"current": {"time": "2026-07-15T12:00", "us_aqi": 162,
                                              "european_aqi": 70, "pm10": 90, "pm2_5": 55, "dust": 20}})
    return CitySnapshot(
        location=Location("Lahore", 31.5497, 74.3436, "Pakistan", "Punjab", "Asia/Karachi"),
        current=current, air=air, outlook=analysis.analyse_hours(rows), hourly=rows,
        air_hourly=[{"time": r["time"], "us_aqi": 160, "pm2_5": 55, "pm10": 90} for r in rows],
        dust_storm_risk="Low",
    )
