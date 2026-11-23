"""Recent earthquakes from the USGS FDSN event service (free, no API key).

https://earthquake.usgs.gov/fdsnws/event/1/ — global catalogue, updated every few minutes.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from .weather_api import get_json

USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def magnitude_class(mag: float | None) -> str:
    """Standard bands: <4 Minor, 4–4.9 Light, 5–5.9 Moderate, 6–6.9 Strong, 7–7.9 Major, 8+ Great."""
    m = mag or 0
    for limit, name in ((4, "Minor"), (5, "Light"), (6, "Moderate"), (7, "Strong"), (8, "Major")):
        if m < limit:
            return name
    return "Great"


def fetch_earthquakes(lat: float, lon: float, radius_km: float = 500, days: int = 7,
                      min_magnitude: float = 2.5, limit: int = 50) -> list[dict[str, Any]]:
    """Earthquakes within ``radius_km`` of a point over the last ``days`` days, newest first."""
    start = (datetime.now(timezone.utc) - timedelta(days=max(1, min(int(days), 30)))).strftime("%Y-%m-%d")
    data = get_json(USGS_URL, {
        "format": "geojson", "latitude": round(lat, 3), "longitude": round(lon, 3),
        "maxradiuskm": max(10, min(float(radius_km), 2000)), "starttime": start,
        "minmagnitude": max(0.0, float(min_magnitude)), "orderby": "time", "limit": max(1, min(int(limit), 200)),
    })
    out = []
    for f in data.get("features") or []:
        p, g = f.get("properties") or {}, (f.get("geometry") or {}).get("coordinates") or [None, None, None]
        if g[0] is None or g[1] is None:
            continue
        when = datetime.fromtimestamp((p.get("time") or 0) / 1000, timezone.utc)
        out.append({
            "time_utc": when.strftime("%Y-%m-%d %H:%M"),
            "magnitude": p.get("mag"),
            "class": magnitude_class(p.get("mag")),
            "place": p.get("place") or "",
            "depth_km": round(float(g[2]), 1) if g[2] is not None else None,
            "distance_km": round(haversine_km(lat, lon, float(g[1]), float(g[0]))),
            "latitude": float(g[1]),
            "longitude": float(g[0]),
            "tsunami": bool(p.get("tsunami")),
            "alert": p.get("alert") or "",
            "url": p.get("url") or "",
        })
    return out


def summarise(quakes: list[dict[str, Any]]) -> dict[str, Any]:
    if not quakes:
        return {"count": 0, "strongest": None, "nearest": None, "latest": None}
    strongest = max(quakes, key=lambda q: q.get("magnitude") or 0)
    nearest = min(quakes, key=lambda q: q["distance_km"] if q.get("distance_km") is not None else 1e9)
    return {"count": len(quakes), "strongest": strongest, "nearest": nearest, "latest": quakes[0]}
