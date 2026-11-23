"""Altair charts for the weather terminal (theme-aware).

Rules applied: one y-axis per chart (no dual axes), 2px lines, 4px rounded bar ends at the
data end, recessive grid, crosshair + tooltip on hover, legend + direct labels for the one
two-series chart, sequential single-hue ramps for heatmaps, status colours only for risk
state (always with a text label).
"""

from __future__ import annotations

from typing import Any

import altair as alt
import pandas as pd

from .. import analysis
from .theme import STATUS, Palette, risk_color

X_AXIS = alt.Axis(format="%H:%M", title=None, labelAngle=0, tickCount=8, grid=False)


def _style(chart, title: str, pal: Palette, subtitle: str = "", height: int = 210):
    title_params = alt.TitleParams(title, subtitle=subtitle) if subtitle else alt.TitleParams(title)
    return (
        chart.properties(height=height, title=title_params)
        .configure(background="transparent", font="Inter")
        .configure_view(strokeWidth=0)
        .configure_axis(gridColor=pal.grid, gridOpacity=0.9, domainColor=pal.axis, tickColor=pal.axis,
                        labelColor=pal.muted, titleColor=pal.muted, labelFontSize=11, titleFontSize=11,
                        titleFontWeight=500)
        .configure_title(color=pal.ink, subtitleColor=pal.muted, anchor="start", fontSize=14, fontWeight=700,
                         subtitleFontSize=11, offset=10)
        .configure_legend(labelColor=pal.ink_2, titleColor=pal.muted, orient="top", direction="horizontal",
                          symbolStrokeWidth=2, labelFontSize=11, title=None)
    )


def hourly_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"])
    df["storm_score"] = [analysis.hour_storm_score(r) for r in rows]
    df["wind_dir"] = [analysis.wind_compass(r.get("wind_direction_10m")) for r in rows]
    df["condition"] = [analysis.describe_code(r.get("weather_code")) for r in rows]
    return df


def _hover(base, tooltip: list, pal: Palette):
    nearest = alt.selection_point(nearest=True, on="pointerover", fields=["time"], empty=False, clear="pointerout")
    selectors = base.mark_rule(strokeWidth=18, opacity=0).encode(tooltip=tooltip).add_params(nearest)
    rule = base.mark_rule(color=pal.muted, strokeWidth=1, strokeDash=[3, 3]).encode(
        opacity=alt.condition(nearest, alt.value(0.8), alt.value(0)))
    return selectors, rule, nearest


def _points(base, y, color: str, nearest, pal: Palette):
    return base.mark_point(color=color, filled=True, size=70, stroke=pal.surface, strokeWidth=2).encode(
        y=y, opacity=alt.condition(nearest, alt.value(1), alt.value(0)))


def line(df: pd.DataFrame, field: str, title: str, unit: str, color: str, pal: Palette, fmt: str = ".1f"):
    base = alt.Chart(df).encode(x=alt.X("time:T", axis=X_AXIS))
    y = alt.Y(f"{field}:Q", title=unit, scale=alt.Scale(zero=False, nice=True))
    selectors, rule, nearest = _hover(base, [
        alt.Tooltip("time:T", title="Time", format="%a %H:%M"),
        alt.Tooltip(f"{field}:Q", title=f"{title} ({unit})", format=fmt),
        alt.Tooltip("condition:N", title="Weather")], pal)
    area = base.mark_area(color=color, opacity=0.12, interpolate="monotone").encode(y=y)
    ln = base.mark_line(color=color, strokeWidth=2, interpolate="monotone").encode(y=y)
    return _style(alt.layer(area, ln, rule, _points(base, y, color, nearest, pal), selectors), title, pal)


def bars(df: pd.DataFrame, field: str, title: str, unit: str, color: str, pal: Palette,
         domain: list | None = None, fmt: str = ".0f", empty_note: str = "No rain expected in this window"):
    base = alt.Chart(df).encode(x=alt.X("time:T", axis=X_AXIS))
    peak = float(pd.to_numeric(df[field], errors="coerce").fillna(0).max())
    scale = alt.Scale(domain=domain or [0, max(1.0, peak * 1.2)])
    selectors, rule, _ = _hover(base, [
        alt.Tooltip("time:T", title="Time", format="%a %H:%M"),
        alt.Tooltip(f"{field}:Q", title=f"{title} ({unit})", format=fmt),
        alt.Tooltip("condition:N", title="Weather")], pal)
    bar = base.mark_bar(color=color, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, width={"band": 0.7}).encode(
        y=alt.Y(f"{field}:Q", title=unit, scale=scale, axis=alt.Axis(format=fmt, tickCount=5)))
    layers = [bar, rule, selectors]
    if peak <= 0:  # say it in words instead of showing an empty plot
        layers.append(alt.Chart(pd.DataFrame({"t": [empty_note]})).mark_text(
            fontSize=13, fontWeight=600, color=pal.ink_2).encode(text="t:N"))
    return _style(alt.layer(*layers), title, pal)


def temperature(df, pal):
    return line(df, "temperature_2m", "Temperature", "°C", pal.orange, pal)


def humidity(df, pal):
    return line(df, "relative_humidity_2m", "Air humidity", "%", pal.blue, pal, ".0f")


def rain_chance(df, pal):
    return bars(df, "precipitation_probability", "Rain chance", "%", pal.blue, pal, domain=[0, 100])


def precipitation(df, pal):
    return bars(df, "precipitation", "Precipitation", "mm", pal.aqua, pal, fmt=".1f")


def wind(df: pd.DataFrame, pal: Palette):
    long = df.melt(id_vars=["time", "wind_dir", "condition"], value_vars=["wind_speed_10m", "wind_gusts_10m"],
                   var_name="series", value_name="kmh")
    long["series"] = long["series"].map({"wind_speed_10m": "Wind", "wind_gusts_10m": "Gusts"})
    color = alt.Color("series:N", scale=alt.Scale(domain=["Wind", "Gusts"], range=[pal.blue, pal.orange]),
                      legend=alt.Legend(title=None))
    base = alt.Chart(long).encode(x=alt.X("time:T", axis=X_AXIS))
    y = alt.Y("kmh:Q", title="km/h", scale=alt.Scale(zero=True))
    hover_base = alt.Chart(df[["time", "wind_speed_10m", "wind_gusts_10m", "wind_dir"]]).encode(x=alt.X("time:T", axis=X_AXIS))
    selectors, rule, nearest = _hover(hover_base, [
        alt.Tooltip("time:T", title="Time", format="%a %H:%M"),
        alt.Tooltip("wind_speed_10m:Q", title="Wind (km/h)", format=".1f"),
        alt.Tooltip("wind_gusts_10m:Q", title="Gusts (km/h)", format=".1f"),
        alt.Tooltip("wind_dir:N", title="From")], pal)
    ln = base.mark_line(strokeWidth=2, interpolate="monotone").encode(
        y=y, color=color, strokeDash=alt.StrokeDash("series:N", legend=None,
                                                    scale=alt.Scale(domain=["Wind", "Gusts"], range=[[1, 0], [5, 3]])))
    pts = base.mark_point(filled=True, size=60, stroke=pal.surface, strokeWidth=2).encode(
        y=y, color=color, opacity=alt.condition(nearest, alt.value(1), alt.value(0)))
    last = long[long["time"] == long["time"].max()]
    labels = alt.Chart(last).mark_text(align="left", dx=6, fontSize=11, fontWeight=600, color=pal.ink_2).encode(
        x="time:T", y="kmh:Q", text="series:N")
    layers = [ln, rule, pts, selectors, labels]
    if float(long["kmh"].max() or 0) >= 40:  # gale line only when in range
        layers += [
            alt.Chart(pd.DataFrame({"y": [62]})).mark_rule(color=STATUS["serious"], strokeDash=[4, 4]).encode(y="y:Q"),
            alt.Chart(pd.DataFrame({"y": [62], "t": ["Gale 62 km/h"]})).mark_text(
                align="left", dy=-6, x=4, fontSize=10, color=pal.ink_2).encode(y="y:Q", text="t:N"),
        ]
    return _style(alt.layer(*layers), "Wind & gusts", pal, "km/h · dashed = gusts")


def storm(df: pd.DataFrame, pal: Palette):
    base = alt.Chart(df).encode(x=alt.X("time:T", axis=X_AXIS))
    y = alt.Y("storm_score:Q", title="score", scale=alt.Scale(domain=[0, 100]))
    selectors, rule, nearest = _hover(base, [
        alt.Tooltip("time:T", title="Time", format="%a %H:%M"),
        alt.Tooltip("storm_score:Q", title="Storm score"),
        alt.Tooltip("condition:N", title="Weather"),
        alt.Tooltip("cape:Q", title="CAPE (J/kg)", format=".0f"),
        alt.Tooltip("wind_gusts_10m:Q", title="Gusts (km/h)", format=".0f")], pal)
    bands = pd.DataFrame({"y": [20, 45, 70], "label": ["Moderate 20", "High 45", "Severe 70"],
                          "c": [STATUS["warning"], STATUS["serious"], STATUS["critical"]]})
    thresholds = alt.Chart(bands).mark_rule(strokeDash=[4, 4], strokeWidth=1, opacity=0.8).encode(
        y="y:Q", color=alt.Color("c:N", scale=None))
    labels = alt.Chart(bands).mark_text(align="left", x=4, dy=-6, fontSize=10, color=pal.ink_2).encode(y="y:Q", text="label:N")
    area = base.mark_area(color=pal.aqua, opacity=0.18, interpolate="monotone").encode(y=y)
    ln = base.mark_line(color=pal.aqua, strokeWidth=2, interpolate="monotone").encode(y=y)
    return _style(alt.layer(thresholds, labels, area, ln, rule, _points(base, y, pal.aqua, nearest, pal), selectors),
                  "Storm score", pal, "0–100 from thunder codes, CAPE, lifted index, gusts, rain")


def aqi(air_rows: list[dict[str, Any]], pal: Palette):
    if not air_rows:
        return None
    df = pd.DataFrame(air_rows)
    if "us_aqi" not in df:
        return None
    df["time"] = pd.to_datetime(df["time"])
    df["category"] = [analysis.aqi_category(v) for v in df["us_aqi"]]
    base = alt.Chart(df).encode(x=alt.X("time:T", axis=X_AXIS))
    y = alt.Y("us_aqi:Q", title="US AQI", scale=alt.Scale(zero=True))
    selectors, rule, nearest = _hover(base, [
        alt.Tooltip("time:T", title="Time", format="%a %H:%M"),
        alt.Tooltip("us_aqi:Q", title="US AQI"),
        alt.Tooltip("category:N", title="Category"),
        alt.Tooltip("pm2_5:Q", title="PM2.5 (µg/m³)", format=".1f"),
        alt.Tooltip("pm10:Q", title="PM10 (µg/m³)", format=".1f")], pal)
    bands = pd.DataFrame({"y": [50, 100, 150, 200], "label": ["Good ≤50", "Moderate ≤100", "Sensitive ≤150", "Unhealthy ≤200"]})
    bands = bands[bands.y <= max(60, float(df["us_aqi"].max() or 0) + 20)]
    rules = alt.Chart(bands).mark_rule(color=pal.axis, strokeDash=[3, 3]).encode(y="y:Q")
    labels = alt.Chart(bands).mark_text(align="left", x=4, dy=-6, fontSize=10, color=pal.muted).encode(y="y:Q", text="label:N")
    ln = base.mark_line(color=pal.blue, strokeWidth=2, interpolate="monotone").encode(y=y)
    return _style(alt.layer(rules, labels, ln, rule, _points(base, y, pal.blue, nearest, pal), selectors),
                  "Air quality forecast", pal, "US AQI with EPA bands")


# ---------------------------------------------------------------- Pakistan views
HEATMAP_METRICS = {
    "Rain chance (%)": ("rain_prob_pct", "blue", [0, 100], ".0f"),
    "Storm score": ("storm_score", "orange", [0, 100], ".0f"),
    "Precipitation (mm)": ("precip_mm", "blue", None, ".1f"),
    "Wind gusts (km/h)": ("gust_kmh", "orange", None, ".0f"),
}


def heatmap(matrix: list[dict[str, Any]], metric: str, pal: Palette, city_order: list[str]):
    """City x hour grid: one sequential hue, near-zero recedes to the surface."""
    field, hue, domain, fmt = HEATMAP_METRICS[metric]
    df = pd.DataFrame(matrix)
    if df.empty:
        return None
    df["time"] = pd.to_datetime(df["time"])
    df[field] = pd.to_numeric(df[field], errors="coerce").fillna(0)
    ramp = list(pal.seq_blue if hue == "blue" else pal.seq_orange)
    dom = domain or [0, max(1.0, float(df[field].max()))]
    rect = alt.Chart(df).mark_rect(cornerRadius=3, stroke=pal.surface, strokeWidth=2).encode(
        x=alt.X("time:O", timeUnit="monthdatehours", title=None,
                axis=alt.Axis(format="%H:%M", labelAngle=0, labelColor=pal.muted, domain=False, ticks=False,
                              labelOverlap=True)),
        y=alt.Y("city:N", sort=city_order, title=None, axis=alt.Axis(domain=False, ticks=False, labelColor=pal.ink_2,
                                                                     labelFontSize=12, labelPadding=8)),
        color=alt.Color(f"{field}:Q", scale=alt.Scale(domain=dom, range=ramp, interpolate="rgb"),
                        legend=alt.Legend(title=metric, orient="top", direction="horizontal", gradientLength=220,
                                          titleColor=pal.muted, labelColor=pal.ink_2)),
        tooltip=[alt.Tooltip("city:N", title="City"), alt.Tooltip("time:T", title="Time", format="%a %H:%M"),
                 alt.Tooltip(f"{field}:Q", title=metric, format=fmt), alt.Tooltip("condition:N", title="Weather"),
                 alt.Tooltip("rain_prob_pct:Q", title="Rain chance (%)"), alt.Tooltip("storm_score:Q", title="Storm score"),
                 alt.Tooltip("gust_kmh:Q", title="Gusts (km/h)", format=".0f")],
    )
    return _style(rect, f"{metric} · city × hour", pal,
                  "darker = more · hover any cell for details", height=max(260, 26 * len(city_order)))


def ranking(table: list[dict[str, Any]], pal: Palette, top: int = 20):
    """Horizontal bars: storm score per city; status colour + risk label at the bar end."""
    df = pd.DataFrame(table[:top])
    if df.empty:
        return None
    df["color"] = [risk_color(r) for r in df["storm_risk"]]
    df["label"] = [f"{r} · {int(s)}" for r, s in zip(df["storm_risk"], df["storm_score"])]
    order = list(df["city"])
    base = alt.Chart(df).encode(y=alt.Y("city:N", sort=order, title=None,
                                        axis=alt.Axis(domain=False, ticks=False, labelColor=pal.ink_2, labelFontSize=12)))
    bar = base.mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4, height={"band": 0.62}).encode(
        x=alt.X("storm_score:Q", title="storm score (0–100)", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("color:N", scale=None),
        tooltip=[alt.Tooltip("city:N", title="City"), alt.Tooltip("storm_risk:N", title="Risk"),
                 alt.Tooltip("storm_score:Q", title="Storm score"), alt.Tooltip("max_rain_prob_pct:Q", title="Max rain chance (%)"),
                 alt.Tooltip("total_precip_mm:Q", title="Total rain (mm)", format=".1f"),
                 alt.Tooltip("max_gust_kmh:Q", title="Max gust (km/h)", format=".0f")])
    text = base.mark_text(align="left", dx=6, fontSize=11, fontWeight=600, color=pal.ink_2).encode(
        x="storm_score:Q", text="label:N")
    return _style(alt.layer(bar, text), "Storm risk ranking", pal, "status colour + label = risk level",
                  height=max(260, 24 * len(df)))


def rain_ranking(table: list[dict[str, Any]], pal: Palette, top: int = 20):
    df = pd.DataFrame(table[:top])
    if df.empty:
        return None
    df = df.sort_values("max_rain_prob_pct", ascending=False)
    order = list(df["city"])
    base = alt.Chart(df).encode(y=alt.Y("city:N", sort=order, title=None,
                                        axis=alt.Axis(domain=False, ticks=False, labelColor=pal.ink_2, labelFontSize=12)))
    bar = base.mark_bar(color=pal.blue, cornerRadiusTopRight=4, cornerRadiusBottomRight=4, height={"band": 0.62}).encode(
        x=alt.X("max_rain_prob_pct:Q", title="max rain chance (%)", scale=alt.Scale(domain=[0, 100])),
        tooltip=[alt.Tooltip("city:N", title="City"), alt.Tooltip("max_rain_prob_pct:Q", title="Max rain chance (%)"),
                 alt.Tooltip("first_rain:N", title="First rain"), alt.Tooltip("total_precip_mm:Q", title="Total (mm)", format=".1f")])
    text = base.mark_text(align="left", dx=6, fontSize=11, fontWeight=600, color=pal.ink_2).encode(
        x="max_rain_prob_pct:Q", text=alt.Text("max_rain_prob_pct:Q", format=".0f"))
    return _style(alt.layer(bar, text), "Rain chance ranking", pal, "highest probability in the window",
                  height=max(260, 24 * len(df)))
