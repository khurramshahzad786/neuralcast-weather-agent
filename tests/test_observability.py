"""LangSmith usage meter with a fake client (nothing is sent to a real LangSmith project)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import langsmith

from weather_agent import config, observability


def _enable(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "fake")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")


def test_meter_off_without_key(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    assert "error" in observability.project_stats()
    assert observability.recent_runs() == []


def test_project_stats_and_runs(monkeypatch):
    _enable(monkeypatch)
    start = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)

    class FakeClient:
        def read_project(self, project_name, include_stats):
            return SimpleNamespace(name=project_name, url="https://smith.example/p/1", run_count=3, total_tokens=4200,
                                   prompt_tokens=4000, completion_tokens=200, total_cost=0, error_rate=1 / 3,
                                   latency_p50=timedelta(seconds=12), latency_p99=timedelta(seconds=40),
                                   last_run_start_time=start)

        def list_runs(self, project_name, is_root, limit):
            return [SimpleNamespace(id="r1", name="weather-agent", status="error", start_time=start,
                                    end_time=start + timedelta(seconds=19), total_tokens=0,
                                    extra={"metadata": {"model": "gemini-3.6-flash", "agent": "weather"}},
                                    error="503 UNAVAILABLE")]

    monkeypatch.setattr(langsmith, "Client", FakeClient)
    stats = observability.project_stats("weather-storm-agent")
    assert stats["run_count"] == 3 and stats["total_tokens"] == 4200 and stats["latency_p50_s"] == 12
    runs = observability.recent_runs("weather-storm-agent")
    assert runs[0]["status"] == "error" and runs[0]["latency_s"] == 19 and runs[0]["model"] == "gemini-3.6-flash"


def test_missing_project_is_friendly(monkeypatch):
    _enable(monkeypatch)

    class FakeClient:
        def read_project(self, **kwargs):
            raise RuntimeError("Project not found")

    monkeypatch.setattr(langsmith, "Client", FakeClient)
    assert "No traces yet" in observability.project_stats("x")["error"]


def test_transient_error_classification():
    assert config.is_transient_error(RuntimeError("503 UNAVAILABLE high demand"))
    assert config.is_transient_error(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert not config.is_transient_error(RuntimeError("400 INVALID_ARGUMENT API key not valid"))
    assert config.is_transient_error(RuntimeError("504 DEADLINE_EXCEEDED. Deadline expired"))
    chain = config.model_chain("gemini-3.6-flash")
    assert chain[0] == "gemini-3.6-flash" and len(set(chain)) == len(chain) == len(config.AVAILABLE_MODELS)


def test_cooling_models_move_to_the_end():
    cooling = {"gemini-3.6-flash": 2000.0, "gemini-3.8-flash": 500.0}  # 3.6 still cooling at t=1000
    chain = config.model_chain("gemini-3.6-flash", cooling, now=1000.0)
    assert chain[0] != "gemini-3.6-flash" and chain[-1] == "gemini-3.6-flash"
    assert "gemini-3.8-flash" in chain[:-1]  # its cooldown expired
