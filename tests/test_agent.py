"""End-to-end Deep Agent wiring with a scripted chat model (no Gemini key, no network)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from weather_agent import agent as wagent
from weather_agent import config, service, vector_store
from weather_agent.usage import UsageTracker


class ScriptedChatModel(BaseChatModel):
    """Returns pre-scripted AIMessages in order; supports bind_tools like a real chat model."""

    script: list[AIMessage]
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any):  # noqa: ARG002
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:  # noqa: ARG002
        msg = self.script[self.calls]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _ai(content: str = "", tool_calls: list[dict] | None = None, tokens: int = 100) -> AIMessage:
    return AIMessage(
        content=content,
        tool_calls=[{"name": n, "args": a, "id": f"call_{i}_{n}", "type": "tool_call"}
                    for i, (n, a) in enumerate(tool_calls or [])],
        usage_metadata={"input_tokens": tokens, "output_tokens": tokens // 4,
                        "total_tokens": tokens + tokens // 4},
        response_metadata={"model_name": "scripted"},
    )


@pytest.fixture
def offline(monkeypatch, snapshot, tmp_path):
    calls: list[tuple] = []

    def fake_snapshot(city, hours=24, country_code=None):
        calls.append((city, hours))
        return snapshot

    monkeypatch.setattr(service, "get_snapshot", fake_snapshot)
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(vector_store, "add_analysis", lambda *a, **k: "doc-1")
    return calls


def test_agent_calls_forecast_saves_pdf_and_answers(offline, tmp_path):
    llm = ScriptedChatModel(script=[
        _ai(tool_calls=[("get_rain_storm_forecast", {"city": "Lahore", "hours": 6})]),
        _ai(tool_calls=[("save_analysis_report", {"analysis_name": "Lahore Storm Watch", "city": "Lahore",
                                                  "analysis_markdown": "## Severe storm risk\n- Gusts 75 km/h"})]),
        _ai("**Lahore Storm Watch**: severe thunderstorm risk around 15:00. PDF saved."),
    ])
    graph = wagent.build_agent(llm=llm, model_name="scripted")
    tracker = UsageTracker()
    result = graph.invoke({"messages": [{"role": "user", "content": "Storm report for Lahore"}]},
                          config={"callbacks": [tracker]})

    assert "severe thunderstorm" in wagent.final_text(result)
    assert wagent.tool_calls_in(result) == ["get_rain_storm_forecast", "save_analysis_report"]
    assert offline[0] == ("Lahore", 6)

    tool_msgs = [m for m in result["messages"] if m.type == "tool"]
    forecast = json.loads(tool_msgs[0].content)
    assert forecast["outlook"]["storm_risk"] == "Severe"
    saved = json.loads(tool_msgs[1].content)
    assert saved["saved"] and saved["indexed_in_vector_db"]
    assert (tmp_path / saved["pdf_file"]).exists()

    usage = tracker.summary()
    assert usage.llm_calls == 3
    assert usage.total_tokens == 3 * 125


def test_agent_delegates_to_storm_subagent(offline):
    llm = ScriptedChatModel(script=[
        # main agent -> built-in `task` tool -> storm-analyst sub-agent
        _ai(tool_calls=[("task", {"subagent_type": "storm-analyst",
                                  "description": "Predict storms in Lahore for the next 6 hours"})]),
        # sub-agent: fetch data, then report
        _ai(tool_calls=[("get_rain_storm_forecast", {"city": "Lahore", "hours": 6})]),
        _ai("Storm analyst: SEVERE risk, thunderstorm at 15:00, gusts 75 km/h."),
        # main agent final answer
        _ai("Final: severe storm expected in Lahore at 15:00."),
    ])
    graph = wagent.build_agent(llm=llm, model_name="scripted")
    result = graph.invoke({"messages": [{"role": "user", "content": "Storms in Lahore?"}]})

    assert wagent.tool_calls_in(result) == ["task"]
    task_result = [m for m in result["messages"] if m.type == "tool"][0].content
    assert "SEVERE" in str(task_result)
    assert offline == [("Lahore", 6)]
    assert wagent.final_text(result).startswith("Final: severe storm")


def test_tool_reports_city_not_found(monkeypatch):
    from weather_agent import tools
    from weather_agent.weather_api import WeatherAPIError

    def boom(*a, **k):
        raise WeatherAPIError("Could not find a city named 'Atlantis'.")

    monkeypatch.setattr(service, "get_snapshot", boom)
    out = json.loads(tools.get_live_weather.invoke({"city": "Atlantis"}))
    assert "Could not find" in out["error"]


def test_subagents_have_required_fields():
    subs = wagent.build_subagents()
    assert {s["name"] for s in subs} == {"storm-analyst", "air-quality-analyst", "pakistan-monitor"}
    for s in subs:
        assert s["description"] and s["system_prompt"] and s["tools"]
