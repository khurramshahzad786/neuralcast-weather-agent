"""AI agent tab: chat (per conversation) + live context panel that follows the conversation.

After every answer the city the agent analysed becomes the portal's focus, so the dashboard,
cards, charts and downloads all update to match what was asked.
"""

from __future__ import annotations

import json
import re
import time

import streamlit as st
from langchain_core.tracers.context import collect_runs

from ... import agent as wagent
from ... import config, quakes, reports, service
from ...agent import AGENT_PROFILES
from ...usage import UsageTracker
from ...weather_api import Location, WeatherAPIError
from .. import components as ui
from .. import state

EXAMPLES = {
    "weather": ["Will it rain or storm in {city} in the next 6 hours?",
                "Scan all Pakistani cities for rain and storms in the next 12 hours",
                "Live wind speed, direction, humidity and AQI in Karachi",
                "Create a news report PDF on the storm outlook for Islamabad (24 h)",
                "Any earthquakes near Quetta this week?",
                "Compare the weather in London and Dubai right now"],
    "pakistan": ["Which Pakistani cities will get rain in the next 12 hours?",
                 "Rank provinces by storm risk for tonight", "Is a thunderstorm likely in Lahore today?"],
    "air": ["How bad is the air quality in {city} today?", "Is it safe to jog in Peshawar this evening?",
            "Dust storm risk in Karachi?"],
    "seismic": ["Earthquakes near {city} in the last 7 days?", "Strongest quake around Islamabad this month (1000 km)?",
                "Any seismic activity near Gilgit?"],
}


def _get_agent(model_name: str, profile: str):
    ss = st.session_state
    key = f"agent::{profile}::{model_name}"
    if key not in ss:
        ss[key] = wagent.build_agent(model_name=model_name, checkpointer=ss.checkpointer, profile=profile,
                                     tz=state.user_tz())
    return ss[key]


def _send_feedback(msg: dict, score: int) -> None:
    """Record 👍/👎 on the answer's LangSmith trace (callback)."""
    from langsmith import Client

    try:
        Client().create_feedback(msg["run_id"], key="user_rating", score=score)
        msg["feedback"] = score
        st.toast("Thanks — your rating was sent to LangSmith ✅")
    except Exception as exc:  # noqa: BLE001 - best-effort UI action
        st.toast(f"Could not send feedback: {exc}")


def _answer_pdf(msg: dict, model_name: str) -> bytes:
    """Build a PDF of an agent answer with live data for its city (generated on click)."""
    loc = Location(**(msg.get("loc") or st.session_state.loc))
    snap = service.get_snapshot_for(loc, 24)
    first = next((ln.strip("# *") for ln in msg["content"].splitlines() if ln.strip()), "")
    title = (first[:70] or f"{loc.name} weather analysis").strip()
    path = reports.build_pdf(snap, title, msg["content"], model_name=model_name, tz=state.user_tz())
    return path.read_bytes()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "answer"


def _message_actions(i: int, m: dict, settings, model_name: str) -> None:
    """Footer under an answer: what the agent did, then clearly labelled actions."""
    st.html(ui.answer_meta(m))
    if m.get("error"):
        st.button("🔁 Resend this question", key=f"resend-{i}", on_click=_resend, args=(i,), type="primary",
                  help="Ask the same question again (the agent will try the free models in turn)")
        return
    bar = st.container(horizontal=True, gap="small", key=f"actions-{i}")
    slug = _slug(m["content"][:40])
    bar.download_button("📄 Download PDF report", lambda: _answer_pdf(m, model_name), file_name=f"{slug}.pdf",
                        mime="application/pdf", key=f"dl-pdf-{i}", on_click="ignore", width="content",
                        help="News-ready PDF: this answer plus live data tables and charts for the city")
    bar.download_button("📝 Download text (.md)", m["content"], file_name=f"{slug}.md", mime="text/markdown",
                        key=f"dl-md-{i}", on_click="ignore", width="content",
                        help="This answer as a Markdown text file you can edit or paste anywhere")
    for j, pdf in enumerate(m.get("pdfs", [])):
        p = config.REPORTS_DIR / pdf
        if p.exists():
            bar.download_button("📎 Agent's saved report", p.read_bytes(), file_name=pdf, mime="application/pdf",
                                key=f"dl-agentpdf-{i}-{j}", on_click="ignore", width="content",
                                help="The PDF the agent saved to the report library during this answer")
    if m.get("run_id") and settings.has_langsmith:
        if m.get("feedback") is None:
            bar.button("👍 Helpful", key=f"up-{i}", on_click=_send_feedback, args=(m, 1), width="content",
                       help="Rate this answer as helpful (sent to LangSmith for evaluation)")
            bar.button("👎 Not helpful", key=f"down-{i}", on_click=_send_feedback, args=(m, 0), width="content",
                       help="Rate this answer as not helpful (sent to LangSmith for evaluation)")
        else:
            bar.html(f'<span class="ans-rated">{"👍" if m["feedback"] else "👎"} Rated — thank you</span>')


def _context_panel(loc_dict: dict) -> None:
    loc = Location(**loc_dict)
    try:
        snap = service.get_snapshot_for(loc, st.session_state.hours)
    except WeatherAPIError as exc:
        st.html(ui.empty(f"⚠ {exc}"))
        return
    try:
        qs = quakes.summarise(quakes.fetch_earthquakes(loc.latitude, loc.longitude, 500, 7))
    except WeatherAPIError:
        qs = None
    st.html(ui.focus_card(snap, qs))
    st.html(ui.section("Next hours", ""))
    st.html(ui.hourly_strip(snap.hourly, limit=12))
    st.caption("This panel, the Dashboard and Downloads follow the city of the latest answer.")


def _stream(agent, payload, run_cfg: dict, calls: list, tools_used: list, pdfs: list) -> None:
    """Stream one agent attempt, showing tool / sub-agent progress live."""
    for namespace, chunk in agent.stream(payload, config=run_cfg, stream_mode="updates", subgraphs=True):
        who = "sub-agent" if namespace else "agent"
        for update in chunk.values():
            msgs = update.get("messages") if isinstance(update, dict) else None
            msgs = getattr(msgs, "value", msgs)  # Overwrite wrapper
            for msg in msgs or []:
                for tc in getattr(msg, "tool_calls", None) or []:
                    name, args = tc.get("name", ""), tc.get("args", {})
                    calls.append({"name": name, "args": args})
                    if not namespace:
                        tools_used.append(name)
                    if name == "task":
                        st.write(f"🧑‍🔬 Delegating to **{args.get('subagent_type')}** — "
                                 f"{str(args.get('description', ''))[:150]}")
                    elif name == "write_todos":
                        st.write("📝 Plan: " + " · ".join(t.get("content", "") for t in args.get("todos", [])))
                    else:
                        brief = {k: v for k, v in args.items() if k != "analysis_markdown"}
                        st.write(f"🔧 {who} → `{name}` {json.dumps(brief, default=str)[:150]}")
                if getattr(msg, "type", "") == "tool" and getattr(msg, "name", "") == "save_analysis_report":
                    try:
                        res = json.loads(msg.content)
                        if res.get("pdf_file"):
                            pdfs.append(res["pdf_file"])
                    except (ValueError, TypeError, AttributeError):
                        pass


def _friendly_error(exc: BaseException, tried: list[str]) -> str:
    text = str(exc)
    if config.is_transient_error(exc):
        why = ("Google's Gemini servers are overloaded or rate-limiting right now (HTTP 503/429). "
               "This is temporary and not a problem with your API key.")
    elif "API key" in text or "PERMISSION_DENIED" in text or "401" in text or "403" in text:
        why = "Gemini rejected the API key. Check `GOOGLE_API_KEY` in `.env` (Configuration shows its status)."
    elif "NOT_FOUND" in text or "404" in text:
        why = "The selected Gemini model is not available for this key. Pick another model in Configuration."
    else:
        why = "Unexpected error while running the agent."
    return (f"⚠️ **The agent could not answer.** {why}\n\nModels tried: {', '.join(tried)}.\n\n"
            f"Details: `{type(exc).__name__}: {text[:300]}`\n\nUse **🔁 Resend** to try again.")


def _run(prompt: str, settings, model_name: str, profile: str) -> None:
    """Run the agent; on Google overload / rate-limit errors fall back to the next free model."""
    ss = st.session_state
    conv = state.active()
    tracker, tools_used, pdfs, calls = UsageTracker(), [], [], []
    cfg_thread = {"configurable": {"thread_id": conv["id"]}}
    answer, run_id, error, used_model, tried = "", None, False, model_name, []
    content = f"{prompt}\n\n{state.time_context()}"  # answers use the user's local time
    with st.status("Analysing live data…", expanded=True) as status, collect_runs() as runs:
        last_exc: BaseException | None = None
        cooling = ss.setdefault("model_cooldown", {})
        chain = config.model_chain(model_name, cooling)
        for attempt, model in enumerate(chain):
            tried.append(model)
            run_cfg = {**cfg_thread, "callbacks": [tracker], "recursion_limit": 80,
                       "run_name": f"{profile}-agent", "tags": ["streamlit", model, profile],
                       "metadata": {"model": model, "agent": profile, "conversation": conv["id"], "attempt": attempt + 1}}
            try:
                agent = _get_agent(model, profile)
                # after a failed attempt the thread is parked mid-run: resume it instead of re-asking
                pending = attempt > 0 and bool(agent.get_state(cfg_thread).next)
                payload = None if pending else {"messages": [{"role": "user", "content": content}]}
                _stream(agent, payload, run_cfg, calls, tools_used, pdfs)
                answer = wagent.final_text(agent.get_state(cfg_thread).values) or "_The agent returned no text._"
                used_model, last_exc = model, None
                break
            except Exception as exc:  # noqa: BLE001 - classify, maybe fall back, else report
                last_exc = exc
                if not config.is_transient_error(exc):
                    break
                cooling[model] = time.time() + config.MODEL_COOLDOWN_S
                if attempt == len(chain) - 1:
                    break
                code = next((c for c in ("503", "504", "429") if c in str(exc)), "busy")
                st.write(f"⏳ `{model}` is overloaded (Google {code}). Switching to `{chain[attempt + 1]}`…")
        if last_exc is not None:
            error, answer = True, _friendly_error(last_exc, tried)
            status.update(label="Agent failed", state="error", expanded=False)
        else:
            label = "Analysis complete" + (f" · answered by {used_model}" if used_model != model_name else "")
            status.update(label=label, state="complete", expanded=False)
        if runs.traced_runs:
            run_id = str(runs.traced_runs[-1].id)
    usage = tracker.summary().as_dict()
    focus = None if error else wagent.focus_from_calls(calls)
    now = state.now_local()
    conv["messages"].append({"role": "assistant", "content": answer, "run_id": run_id, "usage": usage, "error": error,
                             "tools": tools_used, "pdfs": pdfs, "focus": focus, "model": used_model,
                             "prompt": prompt, "time": f"{now:%H:%M} {state.tz_label(now)}"})
    ss.usage_log.append({"question": prompt[:80], "agent": AGENT_PROFILES[profile]["name"], "model": used_model,
                         **{k: usage[k] for k in ("input_tokens", "output_tokens", "total_tokens", "llm_calls")},
                         "tools": ", ".join(tools_used), "status": "error" if error else "ok", "run_id": run_id})
    state.request_focus(focus)


def _resend(index: int) -> None:
    """Drop the failed answer (and its question) and ask the same question again."""
    conv = state.active()
    msgs = conv["messages"]
    failed = msgs[index]
    prompt = failed.get("prompt")
    if prompt is None and index > 0 and msgs[index - 1]["role"] == "user":
        prompt = msgs[index - 1]["content"]
    del msgs[index]
    if index > 0 and msgs[index - 1]["role"] == "user" and msgs[index - 1]["content"] == prompt:
        del msgs[index - 1]
    st.session_state.resend_prompt = prompt


def render(settings, model_name: str, city_hint: str) -> None:
    ss = st.session_state
    conv = state.active()
    profile = conv["agent"]
    spec = AGENT_PROFILES.get(profile, AGENT_PROFILES["weather"])
    left, right = st.columns([3, 2], gap="large")

    with left:
        st.html(ui.section(f"{spec['icon']}  {spec['name']}", conv["title"]))
        if not conv["messages"]:
            st.caption(spec["description"])
        clicked = None
        if not conv["messages"]:
            grid = st.columns(2)
            for i, ex in enumerate(EXAMPLES.get(profile, EXAMPLES["weather"])):
                if grid[i % 2].button(ex.format(city=city_hint), width="stretch", key=f"ex-{profile}-{i}"):
                    clicked = ex.format(city=city_hint)
        thread = st.container()  # messages render here, always above the input box
        with thread:
            for i, m in enumerate(conv["messages"]):
                if m["role"] == "user":
                    with st.chat_message("user", avatar="🧑"), st.container(key=f"msguser-{i}"):
                        st.markdown(m["content"].replace("$", "\\$"))
                    continue
                with st.chat_message("assistant", avatar=spec["icon"]), st.container(key=f"msgai-{i}"):
                    st.html(ui.answer_header(spec["name"], m.get("model", ""), m.get("time", ""), m.get("error")))
                    st.markdown(m["content"].replace("$", "\\$"))  # show $ literally (no LaTeX math)
                    m.setdefault("loc", ss.loc if m.get("focus") else None)
                    _message_actions(i, m, settings, model_name)
        prompt = (st.chat_input(f"Message {spec['name']}…", key="main_prompt") or clicked
                  or ss.pop("resend_prompt", None) or ss.pop("pending_prompt", None))
        if prompt:
            if not settings.has_llm:
                st.error("The AI agent needs `GOOGLE_API_KEY` in the `.env` file. Open ⚙️ Configuration in the "
                         "sidebar for details.")
            else:
                state.set_title_from(prompt)
                conv["messages"].append({"role": "user", "content": prompt})
                with thread:
                    with st.chat_message("user", avatar="🧑"):
                        st.markdown(prompt)
                    with st.chat_message("assistant", avatar=spec["icon"]):
                        _run(prompt, settings, model_name, profile)
                st.rerun()  # redraw every card for the new focus city

    with right:
        _context_panel(ss.loc)
