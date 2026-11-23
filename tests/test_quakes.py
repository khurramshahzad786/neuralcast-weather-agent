from weather_agent import agent as wagent
from weather_agent import quakes

USGS = {"features": [
    {"properties": {"mag": 5.2, "place": "10 km E of A", "time": 1784000000000, "tsunami": 0, "alert": None,
                    "url": "u"}, "geometry": {"coordinates": [67.1, 30.2, 12.0]}},
    {"properties": {"mag": 3.1, "place": "B", "time": 1783990000000, "tsunami": 1}, "geometry": {"coordinates": [67.0, 30.18, 5]}},
]}


def test_fetch_earthquakes_parses_usgs(monkeypatch):
    seen = {}

    def fake(url, params):
        seen.update(params)
        return USGS

    monkeypatch.setattr(quakes, "get_json", fake)
    out = quakes.fetch_earthquakes(30.18, 67.0, radius_km=5000, days=99)
    assert seen["maxradiuskm"] == 2000 and seen["format"] == "geojson"  # clamped
    assert out[0]["magnitude"] == 5.2 and out[0]["class"] == "Moderate" and out[0]["distance_km"] > 0
    assert out[1]["tsunami"] is True
    s = quakes.summarise(out)
    assert s["count"] == 2 and s["strongest"]["magnitude"] == 5.2 and s["nearest"]["place"] == "B"


def test_magnitude_classes():
    assert [quakes.magnitude_class(m) for m in (2.6, 3.9, 4.5, 5.5, 6.5, 7.5, 8.1)] == [
        "Minor", "Minor", "Light", "Moderate", "Strong", "Major", "Great"]


def test_haversine():
    assert 1000 < quakes.haversine_km(24.86, 67.01, 31.55, 74.34) < 1060  # Karachi-Lahore great circle ~1033 km


def test_focus_from_calls_takes_last_city():
    calls = [{"name": "write_todos", "args": {}}, {"name": "get_live_weather", "args": {"city": "Lahore"}},
             {"name": "get_rain_storm_forecast", "args": {"city": "Karachi", "hours": 6}}]
    assert wagent.focus_from_calls(calls) == {"city": "Karachi", "country_code": None, "hours": 6}
    assert wagent.focus_from_calls([{"name": "pakistan_rain_storm_scan", "args": {"hours": 12}}]) is None


def test_time_zone_helpers(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from weather_agent.ui import state

    monkeypatch.setattr(state, "user_tz", lambda: ZoneInfo("Asia/Karachi"))
    assert state.tz_label(datetime(2026, 11, 23, 17, 0, tzinfo=ZoneInfo("Asia/Karachi"))) == "PKT"
    ctx = state.time_context()
    assert "PKT" in ctx and "Asia/Karachi" in ctx


def test_pdf_timestamp_in_user_time_zone(snapshot, tmp_path):
    from zoneinfo import ZoneInfo

    from weather_agent import reports

    path = reports.build_pdf(snapshot, "TZ Check", "text", out_dir=tmp_path, tz=ZoneInfo("Asia/Karachi"))
    assert path.exists()


def test_every_agent_profile_builds():
    from tests.test_agent import ScriptedChatModel

    for key, spec in wagent.AGENT_PROFILES.items():
        graph = wagent.build_agent(llm=ScriptedChatModel(script=[]), model_name="scripted", profile=key)
        assert graph is not None, key
        assert spec["name"] and spec["icon"] and spec["description"]
