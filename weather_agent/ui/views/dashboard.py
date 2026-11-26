"""Dashboard tab: live conditions, hourly + 7-day outlook, analytics, PDF publishing."""

from __future__ import annotations

import streamlit as st

from ... import reports, service, vector_store
from .. import charts
from .. import components as ui
from ..theme import Palette
from .. import state
from . import seismic


BACKUP_NOTICE = ("Open-Meteo is not responding, so this forecast comes from the backup source **MET Norway**. "
                 "Air quality, wind gusts and rain probability return automatically when Open-Meteo is back.")


def render(snap, pal: Palette) -> None:
    if snap.source != "Open-Meteo":
        st.info(BACKUP_NOTICE, icon="🛰️")
    st.html(ui.hero(snap))
    st.html(ui.tiles(snap))

    st.html(ui.section(f"Next {len(snap.hourly)} hours", "hour-by-hour · coloured bar = storm risk"))
    st.html(ui.hourly_strip(snap.hourly))

    if snap.daily:
        st.html(ui.section("7-day outlook", "daily high / low · rain · wind · sunrise–sunset · UV"))
        st.html(ui.daily_cards(snap.daily))

    st.html(ui.section("Forecast analytics", "hover any chart for exact values"))
    df = charts.hourly_frame(snap.hourly)
    if not df.empty:
        for left, right in ((charts.temperature, charts.humidity),
                            (charts.rain_chance, charts.precipitation),
                            (charts.wind, charts.storm)):
            c1, c2 = st.columns(2)
            c1.altair_chart(left(df, pal), width="stretch", theme=None)
            c2.altair_chart(right(df, pal), width="stretch", theme=None)

    c1, c2 = st.columns(2)
    aqi_chart = charts.aqi(snap.air_hourly, pal)
    if aqi_chart is not None:
        c1.altair_chart(aqi_chart, width="stretch", theme=None)
    with c2, st.container(border=True):
        st.markdown("##### 📰 Publish analysis report")
        st.caption("News-ready PDF named after the analysis, indexed for search. For an AI-written "
                   "report, ask the **AI agent** tab.")
        name = st.text_input("Analysis name", value=f"{snap.location.name} Weather & Storm Outlook",
                             key=f"pdf-name-{snap.location.name}")
        if st.button("📄 Generate PDF report", type="primary", width="stretch"):
            text = service.auto_summary(snap)
            path = reports.build_pdf(snap, name, text, model_name="rule-based", tz=state.user_tz(),
                                     owner=state.visitor_id())
            try:
                vector_store.add_analysis(name, snap.location.name, text, path.name, snap.outlook["storm_risk"],
                                          owner=state.visitor_id())
            except Exception as exc:  # noqa: BLE001 - PDF is saved even if vector indexing fails
                st.warning(f"PDF saved, but vector indexing failed: {exc}" if state.is_owner() else
                           "PDF saved. It could not be added to the search archive right now.")  # raw error: owner
            st.success(f"Saved {path.name}")
            st.download_button("⬇ Download PDF", path.read_bytes(), file_name=path.name,
                               mime="application/pdf", key="dash-dl", width="stretch")

    seismic.render(snap.location.latitude, snap.location.longitude, snap.location.name, pal, key="dash-seis")

    with st.expander("📋 Hourly data table"):
        st.html(ui.table(service.compact_hourly(snap.hourly), [
            ("date", "Date"), ("time", "Time"), ("wx", "Weather"), ("temp_c", "Temp °C"), ("rh_pct", "Humidity %"),
            ("rain_prob_pct", "Rain %"), ("precip_mm", "mm"), ("wind_kmh", "Wind km/h"), ("wind_dir", "From"),
            ("gust_kmh", "Gust km/h"), ("cape", "CAPE"), ("storm_score", "Storm score"),
        ]))
