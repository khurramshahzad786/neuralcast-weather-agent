"""NeuralCast by Neural ThinkPad — weather portal + AI weather agents (Streamlit).

Run locally:  streamlit run app.py          (API keys in .env)
Deploy:       Streamlit Community Cloud     (same keys in App settings → Secrets)
"""

from __future__ import annotations

from dataclasses import asdict

import streamlit as st

from weather_agent import config

st.set_page_config(page_title=f"{config.PRODUCT_NAME} · {config.COMPANY_NAME}", page_icon="⛈️", layout="wide",
                   initial_sidebar_state="auto")  # open on desktop, tucked away on phones
config.load_streamlit_secrets(st.secrets)  # Cloud fallback only; local keys come from .env
config.ensure_dirs()

from weather_agent import service, vector_store, weather_api  # noqa: E402
from weather_agent.pakistan import PAKISTAN_CITIES  # noqa: E402
from weather_agent.ui import components as ui  # noqa: E402
from weather_agent.ui import state, theme  # noqa: E402
from weather_agent.ui.views import analyst, dashboard, library, radar, sidebar, telemetry  # noqa: E402
from weather_agent.weather_api import Location, WeatherAPIError  # noqa: E402

settings = config.get_settings()
ss = st.session_state
state.init(st.query_params.get("theme"))
moved_to = state.apply_pending_focus()  # agent answer → move the whole portal to that city

mode = "light" if state.is_light() else "dark"
pal = theme.palette(mode)
st.html(theme.build_css(mode))

model_name = sidebar.render(settings)
if moved_to:
    st.toast(f"Portal updated to {moved_to}", icon="📍")


def _on_quick_pick() -> None:
    if ss.quick_pick != "—":
        ss.loc = state.pk_location(ss.quick_pick)
        ss.q = ""
        ss.quick_pick = "—"


def _on_recent() -> None:
    label = ss.get("recent_pick")
    for r in ss.recent:
        if Location(**r).label == label:
            ss.loc = r
            ss.q = ""
    ss.recent_pick = None


def _toggle_theme() -> None:
    ss.theme_choice = state.THEMES[0] if state.is_light() else state.THEMES[1]
    st.query_params["theme"] = "light" if state.is_light() else "dark"


# ---------------------------------------------------------------- top bar (live clock in the user's time zone)
@st.fragment(run_every="30s")
def _topbar() -> None:
    try:
        vec_count = vector_store.count() if settings.has_llm else None
    except Exception:  # noqa: BLE001 - status indicator only
        vec_count = None
    now = state.now_local()
    st.html(ui.topbar(
        {"weather": True, "llm": settings.has_llm, "langsmith": settings.has_langsmith, "vectors": vec_count is not None},
        vec_count, f"{now:%a %d %b · %H:%M} {state.tz_label(now)}", config.PRODUCT_NAME, config.COMPANY_NAME,
    ))


with st.container(key="head"):  # full-width header card; the theme icon sits in its top-right corner
    _topbar()
    st.button("🌙" if state.is_light() else "☀️", key="theme_btn", on_click=_toggle_theme,
              help="Switch to dark theme" if state.is_light() else "Switch to light theme")

# ---------------------------------------------------------------- command bar (all location controls)
cmd = st.container(key="cmdbar")
bar = cmd.columns([3.6, 3.4, 2.4, 1.6], vertical_alignment="bottom")
query = bar[0].text_input("🔎 Search any city in the world", key="q",
                          placeholder="Type a city: Karachi, Tokyo, New York…").strip()
picked: dict | None = None
if query:
    try:
        matches = weather_api.search_cities(query, 8)
    except WeatherAPIError as exc:
        matches = []
        bar[1].error(str(exc))
    if matches:
        idx = bar[1].selectbox(f"{len(matches)} match(es) — pick one", range(len(matches)),
                               format_func=lambda i: matches[i].label, key=f"match::{query.lower()}")
        picked = asdict(matches[idx])
    else:
        bar[1].selectbox("Matches", [f"No city named “{query}”"], disabled=True, key="match-none")
else:
    bar[1].selectbox("Matches", ["Type in the search box to see matches"], disabled=True, key="match-empty")
bar[2].selectbox("🇵🇰 Quick pick · Pakistan", ["—", *PAKISTAN_CITIES], key="quick_pick", on_change=_on_quick_pick)
hours = bar[3].selectbox("Window", state.HOUR_OPTIONS, format_func=lambda h: f"{h} hours", key="hours")

if picked:
    ss.loc = picked
loc = Location(**ss.loc)
ss.recent = [ss.loc] + [r for r in ss.recent if Location(**r).label != loc.label][:5]
if len(ss.recent) > 1:
    cmd.pills("🕘 Recent", [Location(**r).label for r in ss.recent[1:]], key="recent_pick", on_change=_on_recent)

tab_dash, tab_ai, tab_radar, tab_dl, tab_archive, tab_tele = st.tabs(
    ["🌤  Dashboard", "🤖  AI agent", "🛰  Pakistan radar", "📥  Downloads", "🔎  Archive", "📊  Telemetry"],
    key="main_tab")  # stable identity: the open tab survives reruns (e.g. after an agent answer)

with tab_dash:
    try:
        snap = service.get_snapshot_for(loc, hours)
    except WeatherAPIError as exc:
        snap = None
        st.html(ui.empty(f"⚠ {exc}"))
    if snap:
        dashboard.render(snap, pal)
with tab_ai:
    analyst.render(settings, model_name, loc.name)
with tab_radar:
    radar.render(pal)
with tab_dl:
    library.render_downloads(ss.loc, hours)
with tab_archive:
    library.render_archive(settings)
with tab_tele:
    telemetry.render(settings)

st.html(ui.footer(config.COMPANY_NAME, config.PRODUCT_NAME))
