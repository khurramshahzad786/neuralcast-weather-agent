"""Seismic activity section (USGS): KPIs, map and event table. Used by Dashboard and Radar."""

from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

from ... import quakes
from ...weather_api import WeatherAPIError
from .. import components as ui
from ..theme import STATUS, Palette


def _mag_rgb(mag: float) -> list[int]:
    level = "good" if mag < 4 else "warning" if mag < 5 else "serious" if mag < 6 else "critical"
    h = STATUS[level]
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)] + [200]


def render(lat: float, lon: float, place: str, pal: Palette, radius_km: int = 500, days: int = 7,
           min_mag: float = 2.5, key: str = "seis") -> None:
    st.html(ui.section("Seismic activity", f"USGS live catalogue · {radius_km} km around {place} · last {days} days"))
    try:
        events = quakes.fetch_earthquakes(lat, lon, radius_km, days, min_mag, limit=100)
    except WeatherAPIError as exc:
        st.html(ui.empty(f"⚠ Earthquake data unavailable: {exc}"))
        return
    s = quakes.summarise(events)
    if not events:
        st.html(ui.kpis([
            ("Earthquakes", "0", f"≥ M{min_mag} within {radius_km} km"),
            ("Strongest", "–", "no events"), ("Nearest", "–", "no events"), ("Latest", "–", "no events"),
        ]))
        return
    st.html(ui.kpis([
        ("Earthquakes", str(s["count"]), f"≥ M{min_mag} within {radius_km} km"),
        ("Strongest", f"M{s['strongest']['magnitude']:.1f}", f"{ui._e(s['strongest']['place'])}"),
        ("Nearest", f"{s['nearest']['distance_km']} km", f"M{s['nearest']['magnitude']:.1f} · {ui._e(s['nearest']['place'])}"),
        ("Latest", s["latest"]["time_utc"][5:] + " UTC", f"M{s['latest']['magnitude']:.1f} · {ui._e(s['latest']['place'])}"),
    ]))
    c1, c2 = st.columns([3, 2])
    df = pd.DataFrame(events)
    df["fill"] = [_mag_rgb(m or 0) for m in df["magnitude"]]
    df["radius"] = [8000 * (2 ** max(0.0, (m or 0) - 2.5)) for m in df["magnitude"]]
    centre = pd.DataFrame([{"lat": lat, "lon": lon, "name": place}])
    with c1:
        st.pydeck_chart(pdk.Deck(
            layers=[
                pdk.Layer("ScatterplotLayer", df, get_position="[longitude, latitude]", get_fill_color="fill",
                          get_radius="radius", radius_min_pixels=5, radius_max_pixels=40, pickable=True, stroked=True,
                          get_line_color=[255, 255, 255], line_width_min_pixels=1),
                pdk.Layer("ScatterplotLayer", centre, get_position="[lon, lat]", get_fill_color=[56, 189, 248, 255],
                          get_radius=6000, radius_min_pixels=6, stroked=True, get_line_color=[255, 255, 255],
                          line_width_min_pixels=2),
            ],
            map_provider="carto", map_style=pdk.map_styles.LIGHT if pal.mode == "light" else pdk.map_styles.DARK,
            initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=4.2 if radius_km <= 600 else 3.6),
            tooltip={"html": "<b>M{magnitude} · {class}</b><br/>{place}<br/>{time_utc} UTC · depth {depth_km} km"
                             "<br/>{distance_km} km away",
                     "style": {"backgroundColor": pal.surface, "color": pal.ink, "fontSize": "12px"}},
        ), height=340, key=f"{key}-map")
        st.caption("Blue dot = selected location · circle size and colour + label = magnitude")
    with c2:
        rows = [{**e, "mag_html": ui.quake_pill(e["magnitude"])} for e in events[:12]]
        st.html(ui.table(rows, [("time_utc", "UTC"), ("mag_html", "Magnitude"), ("distance_km", "km"),
                                ("depth_km", "Depth"), ("place", "Place")]))
