"""Enterprise sidebar: brand + user, agent selector, conversations, configuration (bottom)."""

from __future__ import annotations

import streamlit as st

from ... import access, config, vector_store
from ...agent import AGENT_PROFILES
from .. import components as ui
from .. import state


def _owner_access() -> None:
    """Owner sign-in (password from ADMIN_PASSWORD). Public visitors never see owner data."""
    ss = st.session_state
    st.html(ui.side_heading("Owner access"))
    if state.is_owner():
        st.caption("🔓 Owner mode is on: LangSmith usage, raw errors and every visitor's reports are visible.")
        if st.button("🔒 Lock owner mode", key="owner_lock", width="stretch"):
            access.lock(ss)
            st.rerun()
        return
    available, reason = access.owner_mode_status()
    if not available:
        st.caption(reason)
        return
    with st.form("owner_form", border=False):
        st.text_input("Owner password", type="password", key="owner_pw", autocomplete="current-password",
                      placeholder="Owner password")
        st.form_submit_button("🔓 Unlock owner mode", width="stretch", on_click=_try_owner_unlock)
    if ss.get("owner_msg"):
        st.error(ss.pop("owner_msg"))


def _try_owner_unlock() -> None:
    """Form callback: check the password, then wipe the field before the page is drawn (never kept)."""
    ss = st.session_state
    pw = ss.get("owner_pw", "")
    ss.owner_pw = ""
    ok, msg = access.try_unlock(pw, ss)
    ss.owner_msg = "" if ok else msg


def _new() -> None:
    state.new_conversation(st.session_state.agent_key)
    state.open_ai_tab()


def _on_agent_change() -> None:
    # a different agent starts a new chat (an empty current chat is simply reused)
    state.new_conversation(st.session_state.agent_key)


def render(settings) -> str:
    """Draw the sidebar and return the selected Gemini model name."""
    ss = st.session_state
    with st.sidebar:
        st.html(ui.sidebar_brand(config.COMPANY_NAME, config.PRODUCT_NAME, config.PRODUCT_TAGLINE, config.OWNER_NAME))

        st.html(ui.side_heading("Agent"))
        keys = list(AGENT_PROFILES)
        st.selectbox("Agent", keys, key="agent_key", on_change=_on_agent_change, label_visibility="collapsed",
                     format_func=lambda k: f"{AGENT_PROFILES[k]['icon']}  {AGENT_PROFILES[k]['name']}")
        st.caption(AGENT_PROFILES[ss.agent_key]["description"])
        st.button("✏️  New conversation", type="primary", width="stretch", on_click=_new, key="new_conv",
                  help="Start a fresh chat and open the AI agent tab")
        st.html(ui.side_heading("Ask the agent"))
        side_prompt = st.chat_input(f"Ask {AGENT_PROFILES[ss.agent_key]['name']}…", key="side_prompt")
        if side_prompt:
            state.submit_prompt(side_prompt)  # answered in the AI agent tab, which opens automatically
        st.caption("Your question is answered in the 🤖 AI agent tab.")

        st.html(ui.side_heading("Recent conversations"))
        convs = state.history()
        if not convs:
            st.caption("No conversations yet. Ask the AI agent anything — your chats will appear here.")
        for conv in convs[:30]:
            icon = AGENT_PROFILES.get(conv["agent"], AGENT_PROFILES["weather"])["icon"]
            n = len([m for m in conv["messages"] if m["role"] == "user"])
            active = conv["id"] == ss.active_conv
            st.button(f"{icon}  {conv['title']}", key=f"conv-{conv['id']}", width="stretch", on_click=state.open_conversation,
                      args=(conv["id"],), type="tertiary" if not active else "secondary",
                      help=f"Open this chat · {n} question(s) · started {conv['created']} · "
                           f"{AGENT_PROFILES.get(conv['agent'], {}).get('name', '')}")
        if convs:
            st.caption("History is kept for this browser session.")

        # ---- configuration (bottom)
        issues = [] if settings.has_llm else ["Gemini API key missing"]
        owner = state.is_owner()
        st.html(ui.side_heading("Configuration"))
        with st.expander("⚙️  Settings & system status" + (f"  ·  ⚠ {len(issues)}" if issues else ""),
                         expanded=bool(issues)):
            st.html(ui.side_heading("API keys (.env)"))
            st.html(
                ui.key_card(settings.has_llm, "Google Gemini",
                            "Loaded from <code>.env</code>" if settings.has_llm else
                            "Missing — add <code>GOOGLE_API_KEY=</code> to <code>.env</code> and restart")
                + ui.key_card(settings.has_langsmith, "LangSmith",
                              ("Tracing on" if not owner else
                               f"Tracing to <b>{ui._e(settings.langsmith_project)}</b>") if settings.has_langsmith else
                              "Optional — add <code>LANGSMITH_API_KEY=</code> to <code>.env</code>"))
            st.html(ui.side_heading("AI model"))
            model_options = list(config.AVAILABLE_MODELS)
            if settings.model not in model_options:
                model_options.insert(0, settings.model)
            model_name = st.selectbox("Gemini model", model_options, index=model_options.index(settings.model),
                                      key="model_name", label_visibility="collapsed")
            st.caption("If Google is overloaded, the agent automatically falls back to the other free models.")
            try:  # health for everyone; the all-visitor total is shown to the owner only
                vec = vector_store.count() if settings.has_llm else None
            except Exception:  # noqa: BLE001 - status only
                vec = None
            tz = state.user_tz()
            st.html(ui.side_heading("System status"))
            st.html(ui.config_status([
                ("Open-Meteo weather & AQI", True, "Live · free · no key"),
                ("USGS earthquakes", True, "Live · free · no key"),
                ("Google Gemini", settings.has_llm, settings.model if settings.has_llm else "Key missing"),
                ("LangSmith tracing", settings.has_langsmith,
                 ("On" if not owner else settings.langsmith_project) if settings.has_langsmith else "Off"),
                ("Chroma vector DB", vec is not None,
                 ("Unavailable" if vec is None else f"{vec} analyses indexed (all visitors)" if owner else "Ready")
                 if settings.has_llm else "Needs Gemini key"),
                ("Your time zone", True, f"{getattr(tz, 'key', state.tz_label())} ({state.tz_label()}) · from browser"),
            ]))
            if st.button("🗑  Clear all conversations", width="stretch", key="clear_convs"):
                state.clear_all()
                st.rerun()
            _owner_access()
            st.caption(f"{config.PRODUCT_NAME} · © {config.COMPANY_NAME}")
    return model_name
