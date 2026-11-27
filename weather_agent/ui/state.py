"""Per-browser-session state: conversations, agent choice, dashboard focus.

Conversations live in ``st.session_state`` only (never shared between visitors). Each
conversation has its own LangGraph thread id, so the agent remembers context per chat.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st
from langgraph.checkpoint.memory import InMemorySaver

from ..pakistan import PAKISTAN_CITIES
from ..weather_api import Location, WeatherAPIError, geocode
from .theme import THEMES as _THEMES

HOUR_OPTIONS = [6, 12, 24, 48, 72]
THEMES = list(_THEMES)
TABS = ["🌤  Dashboard", "🤖  AI agent", "🛰  Pakistan radar", "📥  Downloads", "🔎  Archive", "📊  Telemetry"]
AI_TAB = TABS[1]


def open_ai_tab() -> None:
    """Bring the AI agent tab to the front (safe from callbacks and before the tabs are drawn)."""
    st.session_state.main_tab = AI_TAB


def submit_prompt(prompt: str) -> None:
    """Queue a question (e.g. typed in the sidebar) for the AI agent tab and show that tab."""
    if prompt and prompt.strip():
        st.session_state.pending_prompt = prompt.strip()
        open_ai_tab()


# ---------------------------------------------------------------- user's local time
def user_tz() -> tzinfo:
    """The visitor's time zone, from their browser (e.g. Asia/Karachi). Falls back to UTC."""
    try:
        name = st.context.timezone
        if name:
            return ZoneInfo(name)
        offset = st.context.timezone_offset  # JS getTimezoneOffset(): minutes *behind* UTC
        if offset is not None:
            return timezone(timedelta(minutes=-int(offset)))
    except (ZoneInfoNotFoundError, AttributeError, RuntimeError, ValueError, TypeError):
        pass
    return timezone.utc


def now_local() -> datetime:
    return datetime.now(user_tz())


def tz_label(dt: datetime | None = None) -> str:
    """Short zone name like 'PKT', or 'UTC+05:00' when the zone has no abbreviation."""
    dt = dt or now_local()
    abbr = dt.strftime("%Z")
    if abbr and not abbr.startswith(("+", "-")):
        return abbr
    return f"UTC{dt.strftime('%z')[:3]}:{dt.strftime('%z')[3:]}"


def time_context() -> str:
    """One line the agent receives with every question, so it answers in the user's local time."""
    now = now_local()
    return (f"(Context: the user's local time is {now:%a %d %b %Y %H:%M} {tz_label(now)}, time zone "
            f"{getattr(user_tz(), 'key', tz_label(now))}. Tool times are local to each city.)")


def pk_location(name: str) -> dict:
    lat, lon, prov = PAKISTAN_CITIES[name]
    return asdict(Location(name, lat, lon, "Pakistan", prov, "Asia/Karachi"))


def init(query_theme: str | None) -> None:
    ss = st.session_state
    ss.setdefault("visitor_id", secrets.token_hex(16))  # owns the reports/analyses made in this session
    ss.setdefault("is_owner", False)
    ss.setdefault("checkpointer", InMemorySaver())
    ss.setdefault("conversations", {})
    ss.setdefault("usage_log", [])
    ss.setdefault("recent", [])
    ss.setdefault("loc", pk_location("Lahore"))
    ss.setdefault("hours", 24)
    ss.setdefault("theme_choice", THEMES[1] if query_theme == "light" else THEMES[0])
    ss.setdefault("agent_key", "weather")
    if not ss.get("active_conv") or ss.active_conv not in ss.conversations:
        new_conversation()


def visitor_id() -> str:
    """Random id of this browser session; tags the reports and analyses it creates.

    Empty outside a session (e.g. a script): an empty owner can only ever be seen by the site owner."""
    return st.session_state.get("visitor_id", "")


def is_owner() -> bool:
    """True after the owner unlocked owner mode with ADMIN_PASSWORD (see access.py)."""
    return bool(st.session_state.get("is_owner"))


def is_light() -> bool:
    return st.session_state.get("theme_choice") == THEMES[1]


def new_conversation(agent_key: str | None = None) -> str:
    """Start a fresh chat. An empty current chat is reused instead of piling up blank ones."""
    ss = st.session_state
    agent = agent_key or ss.get("agent_key", "weather")
    current = ss.conversations.get(ss.get("active_conv") or "")
    if current is not None and not current["messages"]:
        current["agent"] = agent
        return current["id"]
    cid = uuid.uuid4().hex[:12]
    ss.conversations[cid] = {"id": cid, "title": "New conversation", "agent": agent,
                             "messages": [], "created": now_local().strftime("%d %b %H:%M")}
    ss.active_conv = cid
    return cid


def history() -> list[dict]:
    """Conversations that have at least one message, newest first (empty drafts are not listed)."""
    return [c for c in reversed(st.session_state.conversations.values()) if c["messages"]]


def active() -> dict:
    ss = st.session_state
    return ss.conversations[ss.active_conv]


def open_conversation(cid: str) -> None:
    """Switch to a saved chat and show it in the AI agent tab (safe from callbacks)."""
    ss = st.session_state
    if cid not in ss.conversations:
        return
    # drop the empty draft we are leaving, so it never shows up as a phantom entry
    current = ss.conversations.get(ss.get("active_conv") or "")
    if current is not None and not current["messages"] and current["id"] != cid:
        del ss.conversations[current["id"]]
    ss.active_conv = cid
    ss.agent_key = ss.conversations[cid]["agent"]
    open_ai_tab()


def set_title_from(prompt: str) -> None:
    conv = active()
    if conv["title"] == "New conversation":
        conv["title"] = (prompt[:42] + "…") if len(prompt) > 42 else prompt


def clear_all() -> None:
    ss = st.session_state
    ss.conversations = {}
    ss.checkpointer = InMemorySaver()
    for key in [k for k in ss if str(k).startswith("agent::")]:
        del ss[key]
    new_conversation()


def request_focus(focus: dict | None) -> None:
    """Ask the next run to move the whole portal to the city the agent just analysed."""
    if focus:
        st.session_state.pending_focus = focus


def apply_pending_focus() -> str | None:
    """Must run BEFORE the command-bar widgets are created. Returns the new city label."""
    ss = st.session_state
    focus = ss.pop("pending_focus", None)
    if not focus:
        return None
    try:
        loc = geocode(focus["city"], focus.get("country_code"))
    except WeatherAPIError:
        return None
    ss.loc = asdict(loc)
    ss.q = ""
    hours = focus.get("hours")
    if isinstance(hours, int) and hours > 0:
        ss.hours = min(HOUR_OPTIONS, key=lambda h: abs(h - hours))
    return loc.label
