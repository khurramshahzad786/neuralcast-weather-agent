"""Pakistan storm radar: KPIs, risk map, rankings, city x hour heatmap, city board."""

from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

from ... import service
from ...pakistan import PAKISTAN_CITIES
from ...weather_api import WeatherAPIError
from .. import charts
from .. import components as ui
from ..theme import RISK_STATUS, Palette, risk_color
from . import seismic


def _rgb(hex_color: str) -> list[int]:
    return [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]


def render(pal: Palette) -> None:
    st.html(ui.section("Pakistan storm radar", "rain & storm forecast · 20 major cities · one live request"))
    hours = st.select_slider("Look ahead", options=[3, 6, 12, 24, 48], value=12,
                             format_func=lambda h: f"{h} hours", key="pk_hours")
    try:
        table, matrix = service.pakistan_scan(hours)
    except WeatherAPIError as exc:
        st.html(ui.empty(f"⚠ {exc}"))
        return
    if not table:
        st.html(ui.empty("No data returned."))
        return

    df = pd.DataFrame(table)
    top = df.iloc[0]
    wettest = df.sort_values("max_rain_prob_pct", ascending=False).iloc[0]
    st.html(ui.kpis([
        ("Rain expected", f"{int(df.rain_expected.sum())} / {len(df)}", f"cities in the next {hours} h"),
        ("Moderate+ storm risk", str(int((df.storm_risk != "Low").sum())), "storm score ≥ 20"),
        ("Highest storm score", f"{int(top.storm_score)}", f"{ui._e(top.city)} · {ui.status_pill(top.storm_risk)}"),
        ("Wettest city", f"{wettest.max_rain_prob_pct:.0f}%", f"{ui._e(wettest.city)} · max rain chance"),
    ]))

    # map
    df["lat"] = [PAKISTAN_CITIES[c][0] for c in df.city]
    df["lon"] = [PAKISTAN_CITIES[c][1] for c in df.city]
    colors = {lvl: _rgb(risk_color(lvl)) for lvl in RISK_STATUS}
    df["fill"] = [colors.get(r, [130, 145, 167]) + [215] for r in df.storm_risk]
    df["radius"] = 14000 + df.storm_score * 900
    text_rgb = _rgb(pal.ink)
    layers = [
        pdk.Layer("ScatterplotLayer", df, get_position="[lon, lat]", get_fill_color="fill", get_radius="radius",
                  pickable=True, stroked=True, get_line_color=_rgb(pal.surface), line_width_min_pixels=2,
                  radius_min_pixels=7, radius_max_pixels=30),
        pdk.Layer("TextLayer", df, get_position="[lon, lat]", get_text="city", get_size=12, get_color=text_rgb,
                  get_pixel_offset=[0, -18], font_weight=700),
    ]
    st.pydeck_chart(pdk.Deck(
        layers=layers, map_provider="carto", map_style=pdk.map_styles.LIGHT if pal.mode == "light" else pdk.map_styles.DARK,
        initial_view_state=pdk.ViewState(latitude=30.2, longitude=69.5, zoom=4.3),
        tooltip={"html": "<b>{city}</b> · {province}<br/>{now} · {temp_c}°C<br/>Storm risk <b>{storm_risk}</b> "
                         "({storm_score}/100)<br/>Rain chance {max_rain_prob_pct}% · gust {max_gust_kmh} km/h",
                 "style": {"backgroundColor": pal.surface, "color": pal.ink, "fontSize": "12px"}},
    ), height=440)
    st.caption("Dot colour and label = storm risk level · dot size = storm score")

    # heatmap: rain in the coming hours, city by city
    st.html(ui.section("Hour-by-hour across Pakistan", "when and where rain or storms are expected"))
    metric = st.segmented_control("Metric", list(charts.HEATMAP_METRICS), default="Rain chance (%)",
                                  key="pk_metric", label_visibility="collapsed") or "Rain chance (%)"
    city_order = list(df.city)  # sorted by storm score
    hm = charts.heatmap(matrix, metric, pal, city_order)
    if hm is not None:
        st.altair_chart(hm, width="stretch", theme=None)

    c1, c2 = st.columns(2)
    r1, r2 = charts.ranking(table, pal), charts.rain_ranking(table, pal)
    if r1 is not None:
        c1.altair_chart(r1, width="stretch", theme=None)
    if r2 is not None:
        c2.altair_chart(r2, width="stretch", theme=None)

    st.html(ui.section("City board", "sorted by storm score"))
    st.html(ui.city_cards(table))

    seismic.render(30.4, 69.4, "Pakistan", pal, radius_km=1200, days=7, min_mag=3.0, key="pk-seis")

    with st.expander("📋 Full table"):
        rows = [{**r, "risk_html": ui.status_pill(r["storm_risk"])} for r in table]
        st.html(ui.table(rows, [
            ("city", "City"), ("province", "Province"), ("now", "Now"), ("temp_c", "Temp °C"),
            ("humidity_pct", "Humidity %"), ("wind_kmh", "Wind km/h"), ("wind_dir", "From"), ("risk_html", "Storm risk"),
            ("storm_score", "Score"), ("first_rain", "First rain"), ("max_rain_prob_pct", "Max rain %"),
            ("total_precip_mm", "Rain mm"), ("max_gust_kmh", "Max gust"), ("thunderstorm_hours", "Thunder h"),
        ]))
