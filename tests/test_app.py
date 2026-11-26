"""Headless Streamlit app tests (no browser, no network, no real Gemini calls)."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import ROOT
from weather_agent import config, quakes, service, vector_store, weather_api
from weather_agent.weather_api import Location

APP = str(ROOT / "app.py")

PK_ROW = {
    "city": "Lahore", "province": "Punjab", "now": "Thunderstorm", "weather_code": 95, "is_day": True,
    "temp_c": 30, "humidity_pct": 50, "wind_kmh": 10, "wind_dir": "W", "storm_risk": "Severe",
    "storm_score": 80, "rain_expected": True, "first_rain": "2026-07-15T15:00", "max_rain_prob_pct": 85,
    "total_precip_mm": 12.0, "max_gust_kmh": 75, "thunderstorm_hours": 1,
}
PK_MATRIX = [{"city": "Lahore", "time": f"2026-07-15T{h:02d}:00", "rain_prob_pct": 20 * h % 100, "precip_mm": 0.5,
              "storm_score": 10 * h, "gust_kmh": 30, "temp_c": 30, "humidity_pct": 60, "condition": "Rain"}
             for h in range(6)]
QUAKES = [{"time_utc": "2026-07-14 10:00", "magnitude": 4.6, "class": "Light", "place": "20 km N of Quetta",
           "depth_km": 10.0, "distance_km": 120, "latitude": 30.3, "longitude": 67.0, "tsunami": False,
           "alert": "", "url": ""}]


@pytest.fixture
def env(monkeypatch, snapshot, tmp_path):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)  # owner tests set it explicitly
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(service, "get_snapshot_for", lambda loc, hours=24: snapshot)
    monkeypatch.setattr(service, "pakistan_scan", lambda hours=12, cities=None: ([PK_ROW], PK_MATRIX))
    monkeypatch.setattr(service, "pakistan_outlook", lambda hours=12, cities=None: [PK_ROW])
    monkeypatch.setattr(quakes, "fetch_earthquakes", lambda *a, **k: QUAKES)
    monkeypatch.setattr(vector_store, "count", lambda *a, **k: 0)
    monkeypatch.setattr(weather_api, "search_cities", lambda q, count=8, country_code=None: [
        Location("Hyderabad", 25.39, 68.37, "Pakistan", "Sindh", "Asia/Karachi"),
        Location("Hyderabad", 17.38, 78.48, "India", "Telangana", "Asia/Kolkata"),
    ])
    return monkeypatch


@pytest.fixture
def app(env):
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def _html(at) -> str:
    return "\n".join(str(getattr(el, "proto", el)) for el in at.get("html"))


def test_app_renders_portal_without_errors(app):
    assert not app.exception, app.exception
    assert [t.label for t in app.tabs] == [
        "🌤  Dashboard", "🤖  AI agent", "🛰  Pakistan radar", "📥  Downloads", "🔎  Archive", "📊  Telemetry"]
    html = _html(app)
    for marker in ("wt-topbar", "wt-hero", "wt-tiles", "wt-strip", "wt-grid", "wx-icon", "wt-days", "fc-city"):
        assert marker in html, marker
    assert "Air speed" in html and "Air humidity" in html and "US AQI" in html
    assert "20 km N of Quetta" in html  # seismic section


def test_loading_skeleton_first_and_ready_marker_last(app):
    htmls = [str(getattr(el, "proto", el)) for el in app.get("html")]
    overlay = next(i for i, h in enumerate(htmls) if "nc-boot" in h and "nc-sk-hero" in h)
    header = next(i for i, h in enumerate(htmls) if "wt-topbar" in h)
    assert overlay < header  # loading screen is drawn before any real content
    assert "nc-ready" in htmls[-1]  # very last element: page fully drawn -> overlay fades out


def test_enterprise_sidebar(app):
    html = _html(app)
    assert "Neural ThinkPad" in html and "Khurram Shahzad" in html and "NeuralCast" in html
    agent = app.sidebar.selectbox(key="agent_key")
    assert agent.options and len(agent.options) == 4
    assert any("Settings" in e.label for e in app.sidebar.expander)
    assert not app.sidebar.text_input  # no location or key inputs in the sidebar


def test_only_one_new_conversation_button_and_no_phantom_history(app):
    labels = [b.label for b in app.sidebar.button]
    assert sum("New conversation" in lbl for lbl in labels) == 1  # the action, not an empty chat entry
    app.sidebar.button(key="new_conv").click().run()
    app.sidebar.button(key="new_conv").click().run()
    assert len(app.session_state.conversations) == 1  # empty drafts are reused, not piled up
    assert sum("New conversation" in b.label for b in app.sidebar.button) == 1


def test_city_search_offers_matches(app):
    app.text_input(key="q").set_value("Hyderabad").run()
    assert not app.exception, app.exception
    sel = next(s for s in app.selectbox if "match" in s.label.lower())
    assert len(sel.options) == 2


def test_theme_icon_button_in_header(app):
    assert "--page:#0a0f1a" in _html(app)
    btn = app.button(key="theme_btn")
    assert btn.label == "☀️"  # icon only: sun switches to light
    btn.click().run()
    assert not app.exception, app.exception
    assert "--page:#f3f6fb" in _html(app)
    assert app.button(key="theme_btn").label == "🌙"


def test_clock_uses_user_time_zone(env, monkeypatch):
    from zoneinfo import ZoneInfo

    from weather_agent.ui import state

    monkeypatch.setattr(state, "user_tz", lambda: ZoneInfo("Asia/Karachi"))
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert "PKT" in _html(at)
    assert "UTC</span>" not in _html(at)


def test_missing_key_reported_in_configuration(app):
    html = _html(app)
    assert "nt-key bad" in html and "GOOGLE_API_KEY" in html  # red key card in Configuration


def test_generate_pdf_button_creates_downloadable_report(app, tmp_path):
    next(b for b in app.button if "Generate PDF" in b.label).click().run()
    assert not app.exception, app.exception
    pdfs = list(tmp_path.glob("*.pdf"))
    assert len(pdfs) == 1 and (tmp_path / "index.jsonl").exists()


def test_downloads_offer_data_exports(app):
    labels = [d.label for d in app.get("download_button")]
    assert sum("Download" in str(lbl) for lbl in labels) >= 6


def test_answer_to_pdf_export(env, tmp_path):
    from weather_agent.ui.views import analyst

    msg = {"role": "assistant", "content": "## Karachi clear tonight\n- AQI 115",
           "loc": {"name": "Karachi", "latitude": 24.86, "longitude": 67.01, "country": "Pakistan",
                   "admin1": "Sindh", "timezone": "Asia/Karachi"}}
    data = analyst._answer_pdf(msg, "gemini-test")
    assert data[:5] == b"%PDF-"
    assert any(p.name.startswith("karachi-clear-tonight_") for p in tmp_path.glob("*.pdf"))


def _overloaded_graph():
    from langchain_core.language_models.chat_models import BaseChatModel
    from langgraph.checkpoint.memory import InMemorySaver

    from weather_agent import agent as wagent

    class Overloaded(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "overloaded"

        def bind_tools(self, tools, **kwargs):  # noqa: ARG002
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ARG002
            raise RuntimeError("503 UNAVAILABLE. This model is currently experiencing high demand.")

    return wagent.build_agent(llm=Overloaded(), model_name="busy", checkpointer=InMemorySaver())


def test_overloaded_model_falls_back_automatically(env, monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver

    from tests.test_agent import ScriptedChatModel, _ai
    from weather_agent import agent as wagent
    from weather_agent.ui.views import analyst

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-used")
    shared = InMemorySaver()
    good = wagent.build_agent(llm=ScriptedChatModel(script=[_ai("Lahore: clear, no rain.")]), model_name="ok",
                              checkpointer=shared)
    busy = _overloaded_graph()
    busy.checkpointer = shared
    primary = config.get_settings().model  # whatever the configured default is, make it the overloaded one
    monkeypatch.setattr(analyst, "_get_agent", lambda model, profile: busy if model == primary else good)

    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.chat_input(key="main_prompt").set_value("Rain in Lahore?").run()
    assert not at.exception, at.exception
    last = at.session_state.conversations[at.session_state.active_conv]["messages"][-1]
    assert not last["error"] and last["content"] == "Lahore: clear, no rain."
    assert last["model"] != primary  # answered by a fallback model


def test_failed_chat_offers_resend(env, monkeypatch):
    from tests.test_agent import ScriptedChatModel, _ai
    from weather_agent import agent as wagent
    from weather_agent.ui.views import analyst
    from langgraph.checkpoint.memory import InMemorySaver

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-used")
    busy = _overloaded_graph()
    monkeypatch.setattr(analyst, "_get_agent", lambda model, profile: busy)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.chat_input(key="main_prompt").set_value("Rain in Lahore?").run()
    msgs = at.session_state.conversations[at.session_state.active_conv]["messages"]
    assert msgs[-1]["error"] and "overloaded" in msgs[-1]["content"] and "not a problem with your API key" in msgs[-1]["content"]
    resend = next(b for b in at.button if "Resend" in b.label)

    good = wagent.build_agent(llm=ScriptedChatModel(script=[_ai("Now it works.")]), model_name="ok",
                              checkpointer=InMemorySaver())
    monkeypatch.setattr(analyst, "_get_agent", lambda model, profile: good)
    resend.click().run()
    assert not at.exception, at.exception
    msgs = at.session_state.conversations[at.session_state.active_conv]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[-1]["content"] == "Now it works."


def test_prompt_from_sidebar_is_answered_in_ai_tab(env, monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver

    from tests.test_agent import ScriptedChatModel, _ai
    from weather_agent import agent as wagent
    from weather_agent.ui import state
    from weather_agent.ui.views import analyst

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-used")
    graph = wagent.build_agent(llm=ScriptedChatModel(script=[_ai("## Lahore\n| City | Temp |\n|---|---|\n| Lahore | 21 |")]),
                               model_name="scripted", checkpointer=InMemorySaver())
    monkeypatch.setattr(analyst, "_get_agent", lambda model, profile: graph)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.chat_input(key="side_prompt").set_value("Weather in Lahore?").run()
    assert not at.exception, at.exception
    assert at.session_state.main_tab == state.AI_TAB  # the AI agent tab is brought to the front
    msgs = at.session_state.conversations[at.session_state.active_conv]["messages"]
    assert msgs[0]["content"] == "Weather in Lahore?" and msgs[-1]["content"].startswith("## Lahore")
    labels = [b.label for b in at.get("download_button")]
    assert "📄 Download PDF report" in labels and "📝 Download text (.md)" in labels  # clear, labelled actions
    assert "ans-head" in _html(at)


def test_new_conversation_opens_ai_tab(app):
    from weather_agent.ui import state

    app.sidebar.button(key="new_conv").click().run()
    assert app.session_state.main_tab == state.AI_TAB


def test_chat_answer_updates_whole_portal(env, monkeypatch):
    """Ask the agent about Karachi -> answer shown, conversation titled, portal focus moves to Karachi."""
    from tests.test_agent import ScriptedChatModel, _ai
    from weather_agent import agent as wagent
    from weather_agent.ui.views import analyst

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-used")
    llm = ScriptedChatModel(script=[
        _ai(tool_calls=[("get_live_weather", {"city": "Karachi"})]),
        _ai("**Karachi**: clear sky, light SW wind, AQI unhealthy."),
    ])
    from langgraph.checkpoint.memory import InMemorySaver

    graph = wagent.build_agent(llm=llm, model_name="scripted", checkpointer=InMemorySaver())
    monkeypatch.setattr(analyst, "_get_agent", lambda model, profile: graph)

    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.chat_input(key="main_prompt").set_value("Weather in Karachi now?").run()
    assert not at.exception, at.exception
    assert at.session_state.loc["name"] == "Karachi"
    conv = at.session_state.conversations[at.session_state.active_conv]
    assert conv["title"].startswith("Weather in Karachi")
    assert conv["messages"][-1]["content"].startswith("**Karachi**")
    assert any("Karachi" in b.label for b in at.sidebar.button)  # history entry


def _hero_drawn(at) -> bool:
    """True when the dashboard hero card is on the page (ignores the stylesheet, which names every class)."""
    return any("wt-hero" in h and "<style" not in h for h in (str(getattr(el, "proto", el)) for el in at.get("html")))


def test_backup_source_notice_on_dashboard(env, snapshot):
    snapshot.source = "MET Norway"
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    assert any("MET Norway" in i.value for i in at.info)
    assert _hero_drawn(at)  # the dashboard is still drawn from the backup data


def test_dashboard_error_retries_automatically_and_recovers(env, snapshot):
    def down(loc, hours=24):
        raise weather_api.WeatherAPIError("Network error: Open-Meteo did not answer in time")

    env.setattr(service, "get_snapshot_for", down)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    assert "did not answer in time" in _html(at) and not _hero_drawn(at)
    assert any(c.value.startswith("↻ Retrying automatically") for c in at.caption)
    env.setattr(service, "get_snapshot_for", lambda loc, hours=24: snapshot)  # data source is back
    at.button(key="retry_dash").click().run()
    assert _hero_drawn(at) and not any("Retrying automatically" in c.value for c in at.caption)


OWNER_PW = "test-owner-pass-123"  # test value only
STATS = {"project": "p", "url": "https://smith.example/p", "run_count": 19, "total_tokens": 93715,
         "prompt_tokens": 89305, "completion_tokens": 4410, "total_cost": 0.0305, "error_rate": 0.63,
         "latency_p50_s": 6.0, "latency_p99_s": 59.0, "last_run": "2026-11-24T14:38:00+00:00"}


@pytest.fixture
def owner_env(env, monkeypatch, tmp_path, snapshot):
    from weather_agent import access, observability, reports

    access.reset_throttle()
    monkeypatch.setenv("ADMIN_PASSWORD", OWNER_PW)
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setattr(observability, "project_stats", lambda project=None: STATS)
    monkeypatch.setattr(observability, "recent_runs", lambda project=None, limit=15: [])
    reports.build_pdf(snapshot, "Someone Elses Report", "private text", out_dir=tmp_path, owner="other-visitor")
    return monkeypatch


def _all_text(at) -> str:
    parts = [_html(at)] + [m.value for m in at.markdown] + [c.value for c in at.code] + [c.value for c in at.caption]
    return "\n".join(parts)


def _unlock(at, password: str):
    at.text_input(key="owner_pw").input(password)
    next(b for b in at.button if "Unlock owner mode" in str(b.label)).click()
    return at.run()


def test_public_visitor_sees_only_their_own_data(owner_env):
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    text = _all_text(at)
    assert "Your token usage" in text
    for leak in ("LangSmith usage meter", "Traced agent runs", "evals.run_eval", "Open project in LangSmith",
                 "Someone Elses Report", "all visitors"):
        assert leak not in text, leak
    assert "your reports from this browser session" in text


def test_owner_unlock_shows_owner_data_and_lock_hides_it(owner_env):
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    _unlock(at, "not-the-password")
    assert any("Wrong password" in e.value for e in at.error)
    assert "LangSmith usage meter" not in _all_text(at)
    assert "owner_pw" not in at.session_state or at.session_state["owner_pw"] == ""  # wrong guess not kept

    _unlock(at, OWNER_PW)
    assert not at.exception, at.exception
    text = _all_text(at)
    assert "LangSmith usage meter" in text and "Traced agent runs" in text and "evals.run_eval" in text
    assert "Someone Elses Report" in text and "all visitors (owner view)" in text
    assert OWNER_PW not in text
    assert "owner_pw" not in at.session_state or at.session_state["owner_pw"] == ""  # field wiped

    at.button(key="owner_lock").click().run()
    text = _all_text(at)
    assert "LangSmith usage meter" not in text and "Someone Elses Report" not in text


def test_owner_sign_in_hidden_without_admin_password(env, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not [t for t in at.text_input if t.key == "owner_pw"]
    assert any("no ADMIN_PASSWORD" in c.value for c in at.caption)


def test_archive_search_shows_only_own_analyses(owner_env):
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.selectbox(key="arch_mode").set_value("Keyword")
    at.text_input(key="arch_q").input("Someone").run()
    assert not at.exception, at.exception
    assert "Someone Elses Report" not in _all_text(at) and "No matching analyses" in _all_text(at)
    _unlock(at, OWNER_PW)
    at.text_input(key="arch_q").input("Someone").run()
    assert "Someone Elses Report" in _all_text(at)
