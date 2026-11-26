"""Weather analysis & storm-prediction Deep Agent (LangChain Deep Agents + Google Gemini).

Architecture
------------
Main agent ("weather-desk-editor") plans with the built-in ``write_todos`` tool, fetches live
data with weather tools, and delegates focused work to sub-agents via the built-in ``task``
tool:

- ``storm-analyst``       rain / thunderstorm / wind-storm prediction for one city
- ``air-quality-analyst`` AQI, pollution, dust and health advice
- ``pakistan-monitor``    country-wide scan of Pakistani cities

The main agent writes the final answer and, when asked, saves a PDF via
``save_analysis_report`` (which also indexes the analysis in the Chroma vector DB).
"""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.language_models.chat_models import BaseChatModel

from . import tools as wtools
from .config import get_settings

REASONING_BASE = """\
Meteorological reasoning base (apply it, cite the numbers):
- Storm score per hour (0-100) is computed by the tools from WMO weather code, CAPE, lifted
  index, wind gusts, rain probability and rain rate. Risk: <20 Low, 20-44 Moderate, 45-69 High,
  >=70 Severe.
- Thunderstorm = WMO codes 95/96/99 (96/99 include hail).
- CAPE J/kg: <300 weak, 300-1000 moderate, 1000-2500 strong, >2500 extreme instability.
- Lifted index: >0 stable, 0..-3 marginal, -3..-6 unstable, < -6 very unstable.
- Wind gusts km/h: >=50 strong, >=62 gale, >=89 storm. A falling pressure trend
  (several hPa in a few hours) supports approaching storms.
- Rain rate mm/h: <2.5 light, 2.5-7.6 moderate, 7.6-50 heavy, >50 violent (urban flooding risk).
- Air humidity: high humidity + high CAPE favours convection; very low humidity + strong winds +
  high PM10/dust indicates dust storms (Sindh, Balochistan, south Punjab, pre-monsoon).
- Air (wind) direction is reported as compass points; mention where wind comes FROM.
- US AQI: 0-50 Good, 51-100 Moderate, 101-150 Unhealthy for sensitive groups, 151-200 Unhealthy,
  201-300 Very unhealthy, 301+ Hazardous. In Pakistan, Oct-Jan smog in Punjab is common.
"""

MAIN_PROMPT = """\
You are the Weather Desk Editor: an expert meteorologist and news-desk writer who analyses LIVE
weather anywhere in the world and predicts rain and storms in the coming hours, with special
focus on Pakistani cities.

Current UTC time: {now}. Each user message ends with a context line giving the user's local time and
time zone: use it for "today", "tonight", "next hours" and when you mention clock times for the user.

Rules:
1. NEVER invent weather numbers. Always call tools for live data first; quote the values
   (with units and local times) that the tools return.
2. For a single city: call get_live_weather and get_rain_storm_forecast (and get_air_quality
   if air/pollution/AQI is relevant). For complex multi-part requests or deep storm analysis,
   delegate to the `storm-analyst` / `air-quality-analyst` sub-agents with the `task` tool.
3. For "Pakistan", "all cities" or province-wide questions, call pakistan_rain_storm_scan or
   delegate to `pakistan-monitor`.
4. Use write_todos only for multi-step requests (several cities or a full report).
5. Structure answers as: headline, current conditions (temperature, air humidity, air speed,
   air direction, AQI), rain forecast for the next hours, storm assessment with risk level and
   timing, public advice. Use Markdown with short sections and a compact table when useful.
6. If the user asks for a report / PDF / news feed / "save", finish by calling
   save_analysis_report ONCE with a short headline as analysis_name and your full Markdown
   analysis. Then tell the user the PDF file name and that it is in the Reports tab.
7. Use search_past_analyses when the user asks about previous reports or wants comparison.
7b. For earthquakes, tremors or seismic activity call get_recent_earthquakes (USGS live data) and
   report magnitude, distance, depth and time; never guess seismic data.
8. Forecasts are probabilistic: state confidence, and for Pakistan recommend following PMD and
   NDMA official advisories when risk is High or Severe.
9. If a tool returns an error (e.g. city not found), say so and suggest a correction.

{reasoning}
"""

STORM_ANALYST_PROMPT = """\
You are a severe-weather forecaster. Given a city (and optional hours ahead), call
get_rain_storm_forecast (and get_live_weather for current wind/humidity). Produce a concise
storm & rain prediction: risk level, storm score, timing of first rain / peak storm hour,
expected rain totals and intensity, max gusts and wind direction, instability (CAPE, lifted
index), pressure trend, confidence, and safety advice. Quote numbers exactly from the tools.
Return Markdown under 250 words.

{reasoning}
"""

AIR_ANALYST_PROMPT = """\
You are an air-quality and public-health analyst. Call get_air_quality for the city (and
get_live_weather for wind speed/direction and humidity, which drive pollutant dispersion).
Report US AQI and category, PM2.5/PM10/dust, the trend for the next hours, dust-storm risk,
how wind and humidity will affect pollution, and health advice. Markdown, under 200 words.

{reasoning}
"""

PAKISTAN_PROMPT = """\
You monitor all major Pakistani cities. Call pakistan_rain_storm_scan for the requested hours.
Return a Markdown table of cities with rain or storm risk (city, province, storm risk, score,
first rain time, max rain probability, total rain mm, max gust), then a 3-5 bullet national
summary naming the most at-risk cities and provinces. If no rain/storms anywhere, say so and
list the 5 highest-scoring cities anyway. Under 300 words.

{reasoning}
"""


def build_llm(model: str | None = None, temperature: float = 0.2, api_key: str | None = None) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    settings = get_settings()
    kwargs = {}
    key = api_key or settings.google_api_key
    if key:
        kwargs["google_api_key"] = key
    from .config import LLM_MAX_RETRIES, LLM_TIMEOUT_S

    name = model or settings.model
    if not name.startswith("gemini-3"):  # Gemini 3.x uses fixed sampling and ignores temperature
        kwargs["temperature"] = temperature
    return ChatGoogleGenerativeAI(
        model=name,
        max_retries=LLM_MAX_RETRIES,
        timeout=LLM_TIMEOUT_S,
        **kwargs,
    )


def build_subagents() -> list[dict]:
    r = REASONING_BASE
    return [
        {
            "name": "storm-analyst",
            "description": "Predicts rain, thunderstorms and wind storms for ONE city in the coming "
                           "hours using live forecast data. Input: city name and hours ahead.",
            "system_prompt": STORM_ANALYST_PROMPT.format(reasoning=r),
            "tools": [wtools.get_rain_storm_forecast, wtools.get_live_weather],
        },
        {
            "name": "air-quality-analyst",
            "description": "Analyses air quality index, PM2.5/PM10, dust and health advice for ONE city.",
            "system_prompt": AIR_ANALYST_PROMPT.format(reasoning=r),
            "tools": [wtools.get_air_quality, wtools.get_live_weather],
        },
        {
            "name": "pakistan-monitor",
            "description": "Scans all major Pakistani cities for rain and storms in the coming hours "
                           "and ranks them by risk.",
            "system_prompt": PAKISTAN_PROMPT.format(reasoning=r),
            "tools": [wtools.pakistan_rain_storm_scan],
        },
    ]


FOCUSED_RULES = """
Current UTC time: {now}
Rules: never invent numbers — call your tools first and quote values with units and local times.
Answer in Markdown with a headline, the key numbers, a risk/conclusion and public advice. If the user
asks for a report / PDF / news feed, finish by calling save_analysis_report once and tell them the
PDF file name. If a tool returns an error, say so and suggest a correction.

{reasoning}
"""

AGENT_PROFILES: dict[str, dict] = {
    "weather": {
        "name": "Weather & Storm Agent", "icon": "⛈️",
        "description": "Full deep agent: live weather worldwide, rain & storm prediction, AQI, earthquakes, "
                       "Pakistan scans, PDF reports. Plans and delegates to 3 sub-agents.",
        "tools": None, "subagents": True, "prompt": None,
    },
    "pakistan": {
        "name": "Pakistan Storm Desk", "icon": "🇵🇰",
        "description": "Country-wide rain & storm monitoring for 20 Pakistani cities.",
        "tools": ["pakistan_rain_storm_scan", "get_rain_storm_forecast", "get_live_weather"], "subagents": False,
        "prompt": "You run the Pakistan storm desk. Start with pakistan_rain_storm_scan, then drill into the "
                  "riskiest cities with get_rain_storm_forecast. Rank cities, name provinces, give timings, and "
                  "recommend following PMD/NDMA advisories when risk is High or Severe.",
    },
    "air": {
        "name": "Air Quality Analyst", "icon": "🌫️",
        "description": "AQI, PM2.5/PM10, dust and health advice for any city.",
        "tools": ["get_air_quality", "get_live_weather"], "subagents": False,
        "prompt": "You are an air-quality and public-health analyst. Use get_air_quality and get_live_weather "
                  "(wind and humidity drive dispersion). Report US AQI and category, pollutants, the trend for "
                  "the next hours, dust-storm risk and concrete health advice.",
    },
    "seismic": {
        "name": "Seismic & Hazard Monitor", "icon": "🌍",
        "description": "Recent earthquakes near any city (USGS) plus current storm conditions.",
        "tools": ["get_recent_earthquakes", "get_live_weather", "get_rain_storm_forecast"], "subagents": False,
        "prompt": "You monitor natural hazards. Use get_recent_earthquakes for seismic activity (magnitude, "
                  "class, distance, depth, time, tsunami flag) and the weather tools for concurrent storm risk. "
                  "Be factual and calm; recommend official sources (PMD, NDMA, USGS) for warnings.",
    },
}


def build_agent(
    llm: BaseChatModel | None = None,
    model_name: str | None = None,
    checkpointer=None,
    api_key: str | None = None,
    profile: str = "weather",
    tz=None,
    owner: str = "",
    see_all: bool = False,
):
    """Create the compiled Deep Agent graph for an agent profile.

    ``owner`` (visitor id) / ``see_all`` (site owner) scope the report tools: what the agent saves
    is tagged with the visitor, and its archive search only sees that visitor's analyses.

    ``api_key`` (an explicit Gemini key) is threaded into the LLM, the embeddings and the
    tools; it is never put in the shared process environment.
    """
    from deepagents import create_deep_agent

    spec = AGENT_PROFILES.get(profile, AGENT_PROFILES["weather"])
    llm = llm or build_llm(model_name, api_key=api_key)
    name = model_name or getattr(llm, "model", "") or ""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    if spec["prompt"] is None:
        prompt = MAIN_PROMPT.format(now=now, reasoning=REASONING_BASE)
    else:
        prompt = spec["prompt"] + FOCUSED_RULES.format(now=now, reasoning=REASONING_BASE)
    return create_deep_agent(
        model=llm,
        tools=wtools.all_tools(model_name=str(name), api_key=api_key, only=spec["tools"], tz=tz,
                               owner=owner, see_all=see_all),
        system_prompt=prompt,
        subagents=build_subagents() if spec["subagents"] else None,
        checkpointer=checkpointer,
        name=f"{profile}-agent",
    )


def final_text(result: dict) -> str:
    """Extract the final assistant text from an agent result/state."""
    messages = result.get("messages", []) if isinstance(result, dict) else []
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "ai":
            content = msg.content
            if isinstance(content, list):  # Gemini may return content blocks
                text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
            else:
                text = str(content or "")
            if text and text.strip():
                return text
    return ""


def focus_from_calls(calls: list[dict]) -> dict | None:
    """Last city (and hours) the agent looked up — used to sync the dashboard to the conversation."""
    focus = None
    for call in calls:
        args = call.get("args") or {}
        city = args.get("city")
        if isinstance(city, str) and city.strip():
            focus = {"city": city.strip(), "country_code": args.get("country_code"),
                     "hours": args.get("hours") if isinstance(args.get("hours"), int) else None}
    return focus


def tool_calls_in(result: dict) -> list[str]:
    """Names of tools the main agent called during a run (for UI & evaluation)."""
    names: list[str] = []
    for msg in result.get("messages", []) if isinstance(result, dict) else []:
        for tc in getattr(msg, "tool_calls", None) or []:
            names.append(tc.get("name", ""))
    return names
