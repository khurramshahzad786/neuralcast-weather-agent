"""Telemetry tab: session token usage + LangSmith usage meter (project totals and recent traces)."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from ... import observability
from .. import components as ui
from .. import state


@st.cache_data(ttl=60, show_spinner=False)
def _stats(project: str) -> dict:
    return observability.project_stats(project)


@st.cache_data(ttl=60, show_spinner=False)
def _runs(project: str) -> list[dict]:
    return observability.recent_runs(project, limit=15)


def _langsmith(settings) -> None:
    st.html(ui.section("LangSmith usage meter", f"project {settings.langsmith_project} · refreshed every minute"))
    if not settings.has_langsmith:
        st.html(ui.empty("LangSmith is off. Add LANGSMITH_API_KEY (and optionally LANGSMITH_PROJECT) to .env, "
                         "then restart the app."))
        return
    c1, c2 = st.columns([4, 1], vertical_alignment="center")
    if c2.button("⟳ Refresh", key="ls-refresh", width="stretch"):
        _stats.clear()
        _runs.clear()
    stats = _stats(settings.langsmith_project)
    if "error" in stats:
        st.html(ui.empty(stats["error"]))
        return
    if stats.get("url"):
        c1.markdown(f"Traces are arriving in LangSmith ✅ · [Open project in LangSmith ↗]({stats['url']})")
    ok_rate = 100 * (1 - stats["error_rate"])
    last = "–"
    if stats.get("last_run"):
        last_dt = datetime.fromisoformat(stats["last_run"]).astimezone(state.user_tz())
        last = f"{last_dt:%d %b %H:%M} {state.tz_label(last_dt)}"
    st.html(ui.kpis([
        ("Traced agent runs", f"{stats['run_count']:,}", f"last run {ui._e(last)}"),
        ("Tokens (LangSmith)", f"{stats['total_tokens']:,}",
         f"in {stats['prompt_tokens']:,} · out {stats['completion_tokens']:,}"),
        ("Success rate", f"{ok_rate:.0f}%", f"error rate {stats['error_rate'] * 100:.0f}%"),
        ("Latency p50 / p99", f"{stats['latency_p50_s'] or 0:.0f}s",
         f"p99 {stats['latency_p99_s'] or 0:.0f}s · cost ${stats['total_cost']:.4f}"),
    ]))
    runs = _runs(settings.langsmith_project)
    if runs:
        tz = state.user_tz()
        rows = [{**r, "when": r["start_time"].astimezone(tz).strftime("%d %b %H:%M") if r["start_time"] else "–",
                 "status_html": ui.run_status_pill(r["status"])} for r in runs]
        st.html(ui.table(rows, [("when", f"Time ({state.tz_label()})"), ("name", "Trace"), ("agent", "Agent"),
                                ("model", "Model"), ("status_html", "Status"), ("total_tokens", "Tokens"),
                                ("latency_s", "Seconds"), ("error", "Error")]))


def render(settings) -> None:
    log = st.session_state.usage_log
    st.html(ui.section("Token usage", "this browser session · main agent + sub-agents"))
    if log:
        total = lambda k: sum(int(r.get(k) or 0) for r in log)  # noqa: E731
        st.html(ui.kpis([
            ("Agent runs", str(len(log)), f"{sum(r.get('status') == 'error' for r in log)} failed"),
            ("Input tokens", f"{total('input_tokens'):,}", "prompt + tool results"),
            ("Output tokens", f"{total('output_tokens'):,}", "generated text + tool calls"),
            ("Total tokens", f"{total('total_tokens'):,}", f"{total('llm_calls')} LLM calls"),
        ]))
        st.html(ui.table(list(reversed(log)), [
            ("question", "Question"), ("agent", "Agent"), ("model", "Model"), ("status", "Status"),
            ("input_tokens", "In"), ("output_tokens", "Out"), ("total_tokens", "Total"), ("llm_calls", "LLM calls"),
            ("tools", "Tools"),
        ]))
    else:
        st.html(ui.empty("Ask the AI agent something to see token usage here."))

    _langsmith(settings)

    st.html(ui.section("Evaluation", "LangSmith datasets & experiments"))
    st.markdown("Run the offline evaluation suite from a terminal; results appear as experiments in LangSmith:")
    st.code("python -m evals.run_eval            # LangSmith experiment\npython -m evals.run_eval --local    # local only",
            language="bash")
