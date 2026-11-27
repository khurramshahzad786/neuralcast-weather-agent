"""Downloads hub (data exports + PDF library) and archive search (semantic or keyword)."""

from __future__ import annotations

import json
import re

import pandas as pd
import streamlit as st

from ... import quakes, reports, service, vector_store
from ...agent import AGENT_PROFILES
from ...weather_api import Location, WeatherAPIError
from .. import components as ui
from .. import state

RISKS = ["Low", "Moderate", "High", "Severe"]


def _csv(rows: list[dict]) -> str:
    return pd.DataFrame(rows).to_csv(index=False)


def _transcript(conv: dict) -> str:
    agent = AGENT_PROFILES.get(conv["agent"], {}).get("name", conv["agent"])
    now = state.now_local()
    lines = [f"# {conv['title']}", f"_Agent: {agent} · exported {now:%Y-%m-%d %H:%M} {state.tz_label(now)}_", ""]
    for m in conv["messages"]:
        lines += [f"## {'You' if m['role'] == 'user' else agent}", "", m["content"], ""]
    return "\n".join(lines)


def render_downloads(loc_dict: dict, hours: int) -> None:
    loc = Location(**loc_dict)
    stamp = state.now_local().strftime("%Y%m%d-%H%M")
    base = f"{loc.name.lower().replace(' ', '-')}_{stamp}"
    st.html(ui.section("Download centre", f"data exports for {loc.label} · PDF report library"))

    try:
        snap = service.get_snapshot_for(loc, hours)
    except WeatherAPIError as exc:
        snap = None
        st.html(ui.empty(f"⚠ {exc}"))
    try:
        eq = quakes.fetch_earthquakes(loc.latitude, loc.longitude, 500, 7)
    except WeatherAPIError:
        eq = []

    conv = state.active()
    items = []
    if snap:
        items += [
            ("⏱ Hourly forecast", f"{len(snap.hourly)} hours · CSV", _csv(service.compact_hourly(snap.hourly)),
             f"{base}_hourly.csv", "text/csv"),
            ("📅 7-day outlook", f"{len(snap.daily)} days · CSV", _csv(snap.daily), f"{base}_7day.csv", "text/csv"),
            ("🌫 Air quality", "hourly AQI · CSV", _csv(snap.air_hourly), f"{base}_air-quality.csv", "text/csv"),
            ("🧾 Full snapshot", "current + outlook + AQI · JSON",
             json.dumps({**snap.to_dict(include_hourly=True), "daily": snap.daily}, indent=2, default=str),
             f"{base}_snapshot.json", "application/json"),
        ]
    items.append(("🌍 Earthquakes (USGS)", f"{len(eq)} events · 500 km · 7 days · CSV", _csv(eq) if eq else "none\n",
                  f"{base}_earthquakes.csv", "text/csv"))
    items.append(("🇵🇰 Pakistan scan", "20 cities · rain & storm · CSV",
                  lambda: _csv(service.pakistan_outlook(12)), f"pakistan-scan_{stamp}.csv", "text/csv"))
    if conv["messages"]:
        items.append(("💬 Conversation", f"{conv['title']} · Markdown", _transcript(conv),
                      f"conversation_{stamp}.md", "text/markdown"))

    cols = st.columns(4)
    for i, (title, sub, data, fname, mime) in enumerate(items):
        with cols[i % 4], st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(sub)
            st.download_button("⬇ Download", data, file_name=fname, mime=mime, key=f"exp-{i}", on_click="ignore",
                               width="stretch")

    render_reports()


def _download(entry: dict, key: str) -> None:
    path = entry.get("path")
    if path is not None and path.exists():
        st.download_button("⬇ Download", path.read_bytes(), file_name=path.name, mime="application/pdf",
                           key=key, width="stretch")


def _cards(entries: list[dict], prefix: str) -> None:
    for i, e in enumerate(entries):
        with st.container(border=True):
            c1, c2 = st.columns([6, 1], vertical_alignment="center")
            c1.html(ui.report_card(e, state.user_tz()))
            with c2:
                _download(e, f"{prefix}-{i}-{e['file']}")


def _visible() -> list[dict]:
    """Reports this viewer may see: their own session's, or every visitor's for the site owner."""
    return reports.visible_index(state.visitor_id(), see_all=state.is_owner())


def render_reports() -> None:
    entries = _visible()
    who = "all visitors (owner view)" if state.is_owner() else "your reports from this browser session"
    st.html(ui.section("PDF report library", f"{len(entries)} analyses · {who}"))
    if not entries:
        st.html(ui.empty("No reports yet. Publish one from the Dashboard, or ask the AI agent for a report. "
                         "Only reports you create in this browser session are listed here."))
        return
    c1, c2, c3, c4 = st.columns([3, 2, 2, 1.4])
    query = c1.text_input("Search reports", placeholder="name, city, risk, words in the analysis…", key="rep_q")
    risks = c2.multiselect("Storm risk", RISKS, key="rep_risk")
    cities = sorted({e.get("city") for e in entries if e.get("city")})
    city = c3.selectbox("City", ["All cities", *cities], key="rep_city")
    order = c4.selectbox("Sort", ["Newest", "Highest risk", "Name"], key="rep_sort")
    found = reports.search_reports(entries, query, risks or None, None if city == "All cities" else city)
    if order == "Highest risk":
        found.sort(key=lambda e: e.get("storm_score") or 0, reverse=True)
    elif order == "Name":
        found.sort(key=lambda e: str(e.get("analysis_name", "")).lower())
    elif not query:
        found.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    st.caption(f"{len(found)} of {len(entries)} reports")
    if not found:
        st.html(ui.empty("No reports match these filters."))
    _cards(found, "rep")
    st.caption("On Streamlit Cloud, storage resets when the app restarts. Download reports you want to keep.")


STOPWORDS = frozenset(
    "a an and are at be by can do does for from has have how i in is it me my next of on or our the there this "
    "to was what when where which will with you your".split())


def _terms(query: str) -> list[str]:
    """Search words without filler like 'the' / 'in' (which would match every chat); all words if only filler."""
    words = [t for t in re.split(r"\W+", query.lower()) if t]
    return [t for t in words if t not in STOPWORDS] or words


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[#*_`>|]", " ", text)).strip()


def _md(text: str) -> str:
    """Show user / model text literally inside Markdown (no formatting, links or math)."""
    return re.sub(r"([\\`*_{}\[\]()#+!|$<>~])", r"\\\1", text)


def _snippet(text: str, terms: list[str], width: int = 180) -> str:
    low = text.lower()
    pos = min((p for p in (low.find(t) for t in terms) if p >= 0), default=0)
    start = max(0, pos - 60)
    return ("…" if start else "") + text[start:start + width].strip() + ("…" if start + width < len(text) else "")


def chat_matches(convs: list[dict], query: str, city: str | None = None) -> list[dict]:
    """Keyword search over this session's conversations, best match first (newest first on ties)."""
    terms = _terms(query)
    if not terms:
        return []
    found = []
    for conv in convs:
        msgs = [m for m in conv["messages"] if not m.get("error")]  # skip "agent could not answer" notices
        texts = [_plain(str(m.get("content", ""))) for m in msgs]
        hay = " ".join(texts).lower()
        if city and city.lower() not in hay:
            continue
        hits = sum(hay.count(t) for t in terms)
        if not hits:
            continue
        answers = [t for m, t in zip(msgs, texts) if m["role"] == "assistant"]
        best = next((t for t in answers + texts if any(term in t.lower() for term in terms)), "")
        found.append({"conv": conv, "hits": hits, "excerpt": _snippet(best, terms)})
    found.sort(key=lambda f: f["hits"], reverse=True)  # stable: convs arrive newest first
    return found


def _chat_cards(matches: list[dict]) -> None:
    for f in matches[:10]:
        conv = f["conv"]
        agent = AGENT_PROFILES.get(conv["agent"], AGENT_PROFILES["weather"])
        asked = len([m for m in conv["messages"] if m["role"] == "user"])
        with st.container(border=True):
            c1, c2 = st.columns([6, 1], vertical_alignment="center")
            c1.markdown(f"**{agent['icon']} {_md(conv['title'])}**")
            c1.caption(f"{agent['name']} · started {conv['created']} · {asked} question(s)")
            if f["excerpt"]:
                c1.caption(_md(f["excerpt"]))
            c2.button("💬 Open chat", key=f"arch-chat-{conv['id']}", on_click=state.open_conversation,
                      args=(conv["id"],), width="stretch", help="Open this conversation in the AI agent tab")


def render_archive(settings) -> None:
    scope = "all visitors' reports (owner view)" if state.is_owner() else "this browser session"
    st.html(ui.section("Analysis archive", f"your conversations + saved reports · {scope}"))
    modes = ["Semantic (vector DB)", "Keyword"] if settings.has_llm else ["Keyword"]
    c1, c2, c3 = st.columns([4, 2, 2])
    q = c1.text_input("Search past analyses", placeholder="thunderstorm risk in Punjab · dust storm Karachi…", key="arch_q")
    mode = c2.selectbox("Search mode", modes, key="arch_mode",
                        help="Applies to saved reports. Conversations are always matched by keyword.")
    city_f = c3.text_input("City filter", placeholder="optional", key="arch_city")
    if not settings.has_llm:
        st.caption("Semantic search turns on when `GOOGLE_API_KEY` is in `.env` (used for embeddings).")
    if not q:
        st.html(ui.empty("Search everything from this browser session: your conversations with the agent and the "
                         "reports you saved. Type a city, a hazard or a phrase."))
        return

    chats = chat_matches(state.history(), q, city_f or None)
    st.html(ui.section("Your conversations", f"{len(chats)} chat(s) · keyword match · this browser session"))
    if chats:
        _chat_cards(chats)
    else:
        st.caption("No conversation in this browser session mentions these words.")

    st.html(ui.section("Saved reports", f"{mode.split(' (')[0].lower()} search · PDF reports and their analyses"))
    if mode.startswith("Semantic"):
        try:
            hits = vector_store.search(q, k=8, city=city_f or None, owner=state.visitor_id(),
                                       see_all=state.is_owner())
        except Exception as exc:  # noqa: BLE001 - optional subsystem
            st.error(f"Vector search failed: {exc}" if state.is_owner() else
                     "Semantic search is unavailable right now; try Keyword mode.")  # raw errors: owner only
            hits = []
        index = {e["file"]: e for e in _visible()}
        entries = []
        for h in hits:
            e = dict(index.get(h.get("pdf_file") or "", {}))
            e.update({"file": h.get("pdf_file") or "", "analysis_name": h.get("analysis_name"), "city": h.get("city"),
                      "storm_risk": h.get("storm_risk"), "created_at": h.get("created_at"),
                      "summary": f"relevance {h['score']} · {h.get('excerpt', '')}"})
            e.setdefault("size_kb", 0)
            entries.append(e)
    else:
        entries = reports.search_reports(_visible(), q, None, city_f or None)
    st.caption(f"{len(entries)} result(s)")
    if not entries:
        st.html(ui.empty("No matching analyses. A report is saved when you ask the agent for a PDF report "
                         "(for example “…and save a PDF report”) or publish one from the Dashboard."))
    _cards(entries, "arch")
