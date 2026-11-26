"""HTML building blocks for the weather terminal (rendered with ``st.html``)."""

from __future__ import annotations

import math
from datetime import datetime
from html import escape
from typing import Any

from .. import analysis
from ..quakes import magnitude_class
from . import icons
from .theme import STATUS, aqi_color, risk_color

MUTED = "#8291a7"  # gauge sits on the hero's dark gradient in both themes

RISK_GLYPH = {"Low": "✓", "Moderate": "!", "High": "▲", "Severe": "⚠"}


def _e(value: Any) -> str:
    return escape("" if value is None else str(value))


def _fmt(value: Any, digits: int = 0, unit: str = "") -> str:
    if value is None:
        return "–"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _e(value)
    txt = f"{v:.{digits}f}"
    return f"{txt}{unit}"


def _hhmm(iso: str | None) -> str:
    if not iso:
        return "–"
    return iso[-5:]


SHORT_LABELS = {"Unhealthy for sensitive groups": "Sensitive groups", "Very unhealthy": "Very unhealthy"}


def status_pill(level: str, kind: str = "risk", short: bool = False) -> str:
    """Coloured badge with icon + text. ``short`` uses a compact label (full text stays in the hover title)."""
    color = risk_color(level) if kind == "risk" else aqi_color(level)
    cls = "warning" if color == STATUS["warning"] else ""
    glyph = RISK_GLYPH.get(level, "●") if kind == "risk" else "●"
    text = SHORT_LABELS.get(level, level) if short else level
    return (f'<span class="wt-status {cls}" style="background:{color}" title="{_e(level)}">'
            f'<span aria-hidden="true">{glyph}</span>{_e(text)}</span>')


def sidebar_brand(company: str, product: str, tagline: str, owner: str) -> str:
    initials = "".join(w[0] for w in owner.split()[:2]).upper() or "?"
    return (
        '<div class="nt-brand">'
        f'<div class="nt-logo">{icons.weather_icon(95, True, 34)}</div>'
        f'<div><div class="nt-company">{_e(company)}</div>'
        f'<div class="nt-product">{_e(product)}</div><div class="nt-tag">{_e(tagline)}</div></div></div>'
        f'<div class="nt-user"><div class="nt-avatar">{_e(initials)}</div>'
        f'<div><div class="nt-name">{_e(owner)}</div><div class="nt-role">{_e(company)} workspace</div></div>'
        '<span class="nt-online" title="online"></span></div>'
    )


TOOL_LABELS = {
    "get_live_weather": "🌡 Live weather", "get_rain_storm_forecast": "🌧 Rain & storm forecast",
    "get_air_quality": "🌫 Air quality", "pakistan_rain_storm_scan": "🇵🇰 Pakistan scan",
    "get_recent_earthquakes": "🌍 Earthquakes (USGS)", "save_analysis_report": "📄 Saved PDF report",
    "search_past_analyses": "🔎 Archive search", "task": "🧑‍🔬 Sub-agent", "write_todos": "📝 Planning",
}


def answer_header(agent: str, model: str, when: str, error: bool | None = None) -> str:
    bits = [f'<b>{_e(agent)}</b>']
    if model:
        bits.append(f'<span title="Model that answered">{_e(model)}</span>')
    if when:
        bits.append(f'<span title="Your local time">🕒 {_e(when)}</span>')
    state = '<span class="ans-flag bad">Not answered</span>' if error else '<span class="ans-flag ok">Answered</span>'
    return f'<div class="ans-head">{" · ".join(bits)}{state}</div>'


def answer_meta(m: dict[str, Any]) -> str:
    """Plain-language strip: which live data sources the agent used, and what it cost."""
    seen: list[str] = []
    for t in m.get("tools") or []:
        label = TOOL_LABELS.get(t, t)
        if label not in seen:
            seen.append(label)
    chips = "".join(f'<span class="ans-chip">{_e(s)}</span>' for s in seen)
    u = m.get("usage") or {}
    cost = (f'<span class="ans-chip muted" title="Tokens processed by Gemini for this answer">'
            f'{u.get("total_tokens", 0):,} tokens · {u.get("llm_calls", 0)} AI calls</span>') if u else ""
    if not chips and not cost:
        return ""
    head = '<span class="ans-label">Data used</span>' if chips else ""
    return f'<div class="ans-meta">{head}{chips}{cost}</div>'


def run_status_pill(status: str | None) -> str:
    s = (status or "unknown").lower()
    level, glyph = {"success": ("good", "✓"), "error": ("critical", "✕")}.get(s, ("warning", "…"))
    cls = "warning" if level == "warning" else ""
    return f'<span class="wt-status {cls}" style="background:{STATUS[level]}">{glyph} {_e(s)}</span>'


def config_status(rows: list[tuple[str, bool, str]]) -> str:
    """Sidebar system-status list: dot + name on one line, detail underneath (no cramped wrapping)."""
    items = "".join(
        f'<div class="nt-st-row"><span class="nt-dot {"on" if ok else "off"}"></span>'
        f'<div><div class="nt-st-name">{_e(name)}</div><div class="nt-st-note">{_e(note)}</div></div></div>'
        for name, ok, note in rows)
    return f'<div class="nt-st">{items}</div>'


def key_card(ok: bool, title: str, detail: str) -> str:
    cls = "ok" if ok else "bad"
    icon = "🔐" if ok else "🔑"
    return (f'<div class="nt-key {cls}"><span class="nt-key-ic">{icon}</span>'
            f'<div><div class="nt-key-t">{_e(title)}</div><div class="nt-key-d">{detail}</div></div></div>')


def side_heading(text: str) -> str:
    return f'<div class="nt-side-h">{_e(text)}</div>'


def quake_pill(mag: Any) -> str:
    try:
        m = float(mag)
    except (TypeError, ValueError):
        return ""
    level = "good" if m < 4 else "warning" if m < 5 else "serious" if m < 6 else "critical"
    color = STATUS[level]
    cls = "warning" if level == "warning" else ""
    return (f'<span class="wt-status {cls}" style="background:{color}">M{m:.1f} '
            f'{_e(magnitude_class(m))}</span>')


def focus_card(snap, quake_summary: dict | None = None) -> str:
    """Compact live card for the city the conversation is about (updates after each answer)."""
    c, a, o = snap.current, snap.air, snap.outlook
    rain = (f"from {_hhmm(o.get('first_rain_time'))}" if o.get("rain_expected")
            else f"none (max {_fmt(o.get('max_precip_probability_pct'))}%)")
    qs = quake_summary or {}
    quake = "–"
    if qs.get("count"):
        s = qs["strongest"]
        quake = f"{qs['count']} in 7 days · strongest {quake_pill(s.get('magnitude'))}"
    elif quake_summary is not None:
        quake = "none ≥ M2.5 within 500 km (7 days)"
    rows = [
        ("Condition", f"{_e(c.get('condition'))} · {_fmt(c.get('temperature_c'), 1)}°C (feels {_fmt(c.get('feels_like_c'), 1)}°)"),
        ("Air speed / direction", f"{_fmt(c.get('wind_speed_kmh'), 1)} km/h from {_e(c.get('wind_direction'))} {small_arrow(c.get('wind_direction_deg'))}"
                                  f" · gusts {_fmt(c.get('wind_gusts_kmh'), 1)}"),
        ("Air humidity", f"{_fmt(c.get('humidity_pct'))}%"),
        ("Air quality", f"US AQI {_fmt(a.get('us_aqi'))} {status_pill(a.get('category', 'Unknown'), 'aqi')}"),
        (f"Rain · next {o.get('hours', 0)} h", rain),
        ("Storm risk", f"{status_pill(o.get('storm_risk', 'Unknown'))} score {o.get('max_storm_score', 0)}/100"),
        ("Earthquakes", quake),
    ]
    body = "".join(f'<div class="fc-row"><span>{k}</span><b>{v}</b></div>' for k, v in rows)
    return (f'<div class="fc"><div class="fc-head"><div><div class="wt-label">Live context</div>'
            f'<div class="fc-city">{_e(snap.location.name)}</div><div class="fc-sub">{_e(snap.location.label)}</div></div>'
            f'{icons.weather_icon(c.get("weather_code"), c.get("is_day", True), 64)}</div>{body}</div>')


def topbar(status: dict[str, bool], vectors: int | None, updated: str, product: str = "NeuralCast",
           company: str = "Neural ThinkPad") -> str:
    def pill(name: str, on: bool, extra: str = "") -> str:
        state = "on" if on else "off"
        return f'<span class="wt-pill"><span class="wt-dot {state}"></span>{_e(name)}{extra}</span>'

    pills = [
        pill("OPEN-METEO", status.get("weather", True)),
        pill("USGS QUAKES", status.get("quakes", True)),
        pill("GEMINI", status.get("llm", False)),
        pill("LANGSMITH", status.get("langsmith", False)),
        pill("VECTOR DB", status.get("vectors", False), f" · {vectors}" if vectors is not None else ""),
        f'<span class="wt-pill wt-clock" title="Your local time (from your browser)">🕒 {_e(updated)}</span>',
    ]
    head = _e(product)
    if head.lower().startswith("neural"):
        head = f"Neural<b>{head[6:]}</b>"
    return (
        '<div class="wt-topbar"><div class="wt-brand">'
        + icons.weather_icon(2, True, 40)
        + f'<div><div class="name">{head} · Weather Portal</div>'
          f'<div class="sub">by {_e(company)} · live data · storm prediction · AI agents</div></div></div>'
        f'<div class="wt-pills">{"".join(pills)}</div></div>'
    )


def section(title: str, sub: str = "") -> str:
    return f'<div class="wt-section"><h3>{_e(title)}</h3><span>{_e(sub)}</span></div>'


def risk_gauge(score: int, level: str, size: int = 190) -> str:
    """Semicircle gauge 0-100 coloured by status, with the level label (never colour alone)."""
    color = risk_color(level)
    r, cx, cy = 80, 100, 96
    length = math.pi * r
    filled = max(0.0, min(100.0, float(score))) / 100 * length
    angle = math.radians(180 - 1.8 * max(0, min(100, score)))
    nx, ny = cx + (r - 14) * math.cos(angle), cy - (r - 14) * math.sin(angle)
    ticks = ""
    for t in (20, 45, 70):  # risk thresholds
        a = math.radians(180 - 1.8 * t)
        x1, y1 = cx + (r - 11) * math.cos(a), cy - (r - 11) * math.sin(a)
        x2, y2 = cx + (r + 11) * math.cos(a), cy - (r + 11) * math.sin(a)
        ticks += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#0a0f1a" stroke-width="2.5"/>'
    arc = f"M{cx - r} {cy} A{r} {r} 0 0 1 {cx + r} {cy}"
    body = (
        f'<path d="{arc}" fill="none" stroke="#223049" stroke-width="16" stroke-linecap="round"/>'
        f'<path d="{arc}" fill="none" stroke="{color}" stroke-width="16" stroke-linecap="round" '
        f'stroke-dasharray="{filled:.1f} {length:.1f}"/>'
        f"{ticks}"
        f'<line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="#eef2f8" stroke-width="3.5" stroke-linecap="round"/>'
        f'<circle cx="{cx}" cy="{cy}" r="6" fill="#eef2f8"/>'
        f'<text x="{cx}" y="{cy + 24}" text-anchor="middle" fill="#eef2f8" font-size="20" font-weight="800" '
        f'font-family="Inter,Segoe UI,system-ui,sans-serif">{score}'
        f'<tspan fill="{MUTED}" font-size="12" font-weight="600">/100</tspan></text>'
    )
    return icons.to_img(body, size, int(size * 0.62), f"Storm score {score} of 100, {level} risk",
                        view_box="0 0 200 124", css_class="wt-gauge")


def compass(deg: Any, size: int = 74) -> str:
    """Wind compass; arrow points where the wind blows TO (from + 180°)."""
    try:
        d = float(deg)
    except (TypeError, ValueError):
        d = None
    ticks = "".join(
        f'<line x1="32" y1="5" x2="32" y2="{9 if i % 2 == 0 else 7}" stroke="#46566f" stroke-width="1.5" '
        f'transform="rotate({i * 45} 32 32)"/>' for i in range(8))
    arrow = ""
    if d is not None:
        arrow = (f'<g transform="rotate({(d + 180) % 360:.0f} 32 32)">'
                 '<path d="M32 12 L38 30 L32 27 L26 30 Z" fill="#38bdf8"/>'
                 '<line x1="32" y1="27" x2="32" y2="50" stroke="#38bdf8" stroke-width="2.5" stroke-linecap="round"/></g>')
    body = ('<circle cx="32" cy="32" r="28" fill="#0f1726" stroke="#2a3953" stroke-width="1.5"/>' + ticks +
            '<text x="32" y="19" text-anchor="middle" font-size="7" font-weight="700" fill="#8291a7" '
            'font-family="Segoe UI,system-ui,sans-serif">N</text>'
            + arrow + '<circle cx="32" cy="32" r="3" fill="#eef2f8"/>')
    return icons.to_img(body, size, size, "wind direction compass", css_class="wt-compass")


def small_arrow(deg: Any) -> str:
    try:
        rot = (float(deg) + 180) % 360
    except (TypeError, ValueError):
        return ""
    body = f'<g transform="rotate({rot:.0f} 6 6)"><path d="M6 1 L10 10 L6 8 L2 10 Z" fill="#7dd3fc"/></g>'
    return icons.to_img(body, 12, 12, "wind direction", view_box="0 0 12 12", css_class="wt-arrow")


def hero(snap) -> str:
    c, o, a = snap.current, snap.outlook, snap.air
    code = c.get("weather_code")
    key = icons.code_to_key(code, c.get("is_day", True))
    top, bottom = icons.MOODS.get(key, icons.MOODS["unknown"])
    bg = (f"background: radial-gradient(700px 320px at 15% 0%, {top}55, transparent 65%),"
          f"linear-gradient(135deg, {bottom}, #0d1526 70%);")
    temps = [r.get("temperature_2m") for r in snap.hourly if r.get("temperature_2m") is not None]
    hi_lo = f"H {_fmt(max(temps))}° · L {_fmt(min(temps))}°" if temps else ""
    local = (c.get("time") or "").replace("T", " · ")
    level = o.get("storm_risk", "Unknown")
    rain_line = (f"from <b>{_hhmm(o.get('first_rain_time'))}</b>" if o.get("rain_expected") else "<b>none expected</b>")
    thunder = len(o.get("thunderstorm_hours") or [])
    return f"""
<div class="wt-hero" style="{bg}">
  <div>
    <div class="wt-label">Live conditions · local {escape(local)}</div>
    <div class="wt-place" style="margin-top:6px">{_e(snap.location.name)}</div>
    <div class="wt-region">{_e(', '.join(p for p in (snap.location.admin1, snap.location.country) if p))}
      · {snap.location.latitude:.2f}°, {snap.location.longitude:.2f}°</div>
    <div class="wt-now">
      {icons.weather_icon(code, c.get('is_day', True), 128)}
      <div>
        <div class="wt-temp">{_fmt(c.get('temperature_c'), 1)}<sup>°C</sup></div>
        <div class="wt-cond">{_e(c.get('condition'))}</div>
      </div>
    </div>
    <div class="wt-meta">
      <span>Feels like <b>{_fmt(c.get('feels_like_c'), 1)}°</b></span>
      <span>{_e(hi_lo)}</span>
      <span>Wind <b>{_fmt(c.get('wind_speed_kmh'), 1)} km/h {_e(c.get('wind_direction'))}</b></span>
      <span>Humidity <b>{_fmt(c.get('humidity_pct'))}%</b></span>
      <span>AQI <b>{_fmt(a.get('us_aqi'))}</b></span>
    </div>
  </div>
  <div class="wt-risk">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div class="wt-label">Storm risk · next {o.get('hours', 0)} h</div>{status_pill(level)}
    </div>
    <div style="display:flex;justify-content:center;margin-top:6px">{risk_gauge(int(o.get('max_storm_score', 0)), level)}</div>
    <div class="wt-facts">
      <div class="wt-fact"><div class="v">{rain_line}</div><div class="k">Rain</div></div>
      <div class="wt-fact"><div class="v">{_fmt(o.get('max_precip_probability_pct'))}%</div><div class="k">Peak rain chance · {_hhmm(o.get('max_precip_probability_time'))}</div></div>
      <div class="wt-fact"><div class="v">{_fmt(o.get('total_precip_mm'), 1)} mm</div><div class="k">Total rain · {_e(o.get('peak_rain_intensity'))}</div></div>
      <div class="wt-fact"><div class="v">{_fmt(o.get('max_gust_kmh'))} km/h</div><div class="k">Max gust · {_hhmm(o.get('max_gust_time'))}</div></div>
      <div class="wt-fact"><div class="v">{thunder} h</div><div class="k">Thunderstorm hours</div></div>
      <div class="wt-fact"><div class="v">{_fmt(o.get('max_cape_jkg'))} J/kg</div><div class="k">Max CAPE (instability)</div></div>
    </div>
  </div>
</div>"""


def _tile(label: str, glyph: str, big: str, note: str, extra: str = "") -> str:
    return (f'<div class="wt-tile"><div class="head"><span class="wt-label">{_e(label)}</span>{glyph}</div>'
            f'<div class="big">{big}</div><div class="note">{note}</div>{extra}</div>')


def _bar(pct: float, color: str) -> str:
    pct = max(0.0, min(100.0, pct))
    return f'<div class="wt-bar"><i style="width:{pct:.0f}%;background:{color}"></i></div>'


def tiles(snap) -> str:
    c, a, o = snap.current, snap.air, snap.outlook
    force, name = analysis.beaufort(c.get("wind_speed_kmh"))
    hum = float(c.get("humidity_pct") or 0)
    dew = next((r.get("dew_point_2m") for r in snap.hourly[:1]), None)
    aqi = a.get("us_aqi")
    aqi_pct = min(100.0, float(aqi or 0) / 300 * 100)
    trend = float(o.get("pressure_trend_hpa") or 0)
    arrow = "▲" if trend > 0.4 else ("▼" if trend < -0.4 else "▬")
    vis = next((r.get("visibility") for r in snap.hourly[:1]), None)
    vis_km = f"{float(vis) / 1000:.0f} km" if vis is not None else "–"
    wind_tile = (
        '<div class="wt-tile wide"><div class="head"><span class="wt-label">Air speed &amp; direction</span>'
        f'{icons.wind_glyph(26)}</div>'
        '<div style="display:flex;align-items:center;gap:12px">'
        f'{compass(c.get("wind_direction_deg"))}'
        f'<div><div class="big">{_fmt(c.get("wind_speed_kmh"), 1)}<small>km/h</small></div>'
        f'<div class="note">from <b>{_e(c.get("wind_direction"))}</b> ({_fmt(c.get("wind_direction_deg"))}°)</div></div></div>'
        f'<div class="note">Gusts {_fmt(c.get("wind_gusts_kmh"), 1)} km/h · Beaufort {force} {_e(name)}</div></div>'
    )
    return '<div class="wt-tiles">' + "".join([
        wind_tile,
        _tile("Air humidity", icons.droplet(26), f"{_fmt(hum)}<small>%</small>",
              f"Dew point {_fmt(dew, 1)}°C", _bar(hum, "#3987e5")),
        _tile("Air quality · US AQI", icons.leaf(26), f"{_fmt(aqi)}",
              f"{status_pill(a.get('category', 'Unknown'), 'aqi', short=True)}<br>PM2.5 {_fmt(a.get('pm2_5'), 1)} µg/m³",
              _bar(aqi_pct, aqi_color(a.get("category", "")))),
        _tile("Pressure", icons.gauge_glyph(26), f"{_fmt(c.get('pressure_hpa'))}<small>hPa</small>",
              f"{arrow} {trend:+.1f} hPa over {o.get('hours', 0)} h"),
        _tile("Clouds & visibility", icons.cloud_glyph(26), f"{_fmt(c.get('cloud_cover_pct'))}<small>%</small>",
              f"Visibility {vis_km}", _bar(float(c.get("cloud_cover_pct") or 0), "#8291a7")),
        _tile("Dust storm", icons.dust_glyph(26), _e(snap.dust_storm_risk),
              f"Dust {_fmt(a.get('dust'))} µg/m³<br>PM10 {_fmt(a.get('pm10'))} µg/m³"),
    ]) + "</div>"


def hourly_strip(rows: list[dict[str, Any]], limit: int = 48) -> str:
    cards = []
    for i, r in enumerate(rows[:limit]):
        score = analysis.hour_storm_score(r)
        level = analysis.risk_level(score)
        flag_color = risk_color(level) if level != "Low" else "transparent"
        t = r.get("time", "")
        label = "Now" if i == 0 else t[-5:]
        day = ""
        if t[-5:] == "00:00" and i:
            try:
                day = datetime.fromisoformat(t).strftime("%a")
            except ValueError:
                day = ""
        pop = r.get("precipitation_probability")
        cards.append(
            f'<div class="wt-hour{" now" if i == 0 else ""}" title="{escape(analysis.describe_code(r.get("weather_code")))} · storm score {score}">'
            f'<div class="t">{_e(day or label)}</div>'
            f'{icons.weather_icon(r.get("weather_code"), bool(r.get("is_day", 1)), 44)}'
            f'<div class="temp">{_fmt(r.get("temperature_2m"))}°</div>'
            f'<div class="pop">💧 {_fmt(pop)}%</div>'
            f'<div class="wind">{small_arrow(r.get("wind_direction_10m"))} {_fmt(r.get("wind_speed_10m"))} km/h</div>'
            f'<div class="flag" style="background:{flag_color}" aria-label="{escape(level)} storm risk"></div>'
            "</div>"
        )
    return f'<div class="wt-strip">{"".join(cards)}</div>'


def kpis(items: list[tuple[str, str, str]]) -> str:
    return '<div class="wt-kpis">' + "".join(
        f'<div class="wt-kpi"><div class="wt-label">{_e(k)}</div><div class="v">{v}</div><div class="s">{s}</div></div>'
        for k, v, s in items) + "</div>"


def city_cards(table: list[dict[str, Any]]) -> str:
    cards = []
    for r in table:
        rain = (f"🌧 from {_hhmm(r.get('first_rain'))}" if r.get("rain_expected") else "No rain")
        cards.append(
            '<div class="wt-city"><div class="row"><div><div class="nm">' + _e(r["city"]) + '</div>'
            f'<div class="pr">{_e(r.get("province"))}</div></div>'
            f'{icons.weather_icon(r.get("weather_code"), bool(r.get("is_day", True)), 46)}</div>'
            f'<div class="row"><div class="tp">{_fmt(r.get("temp_c"))}°</div>{status_pill(r.get("storm_risk", "Unknown"))}</div>'
            f'<div class="kv"><span>{_e(r.get("now"))}</span></div>'
            f'<div class="kv"><span>{rain}</span><span>💧 {_fmt(r.get("max_rain_prob_pct"))}%</span>'
            f'<span>🌬 {_fmt(r.get("wind_kmh"))} km/h {_e(r.get("wind_dir"))}</span>'
            f'<span>Gust {_fmt(r.get("max_gust_kmh"))}</span><span>Score {r.get("storm_score", 0)}</span></div></div>'
        )
    return f'<div class="wt-grid">{"".join(cards)}</div>'


def daily_cards(days: list[dict[str, Any]]) -> str:
    """7-day outlook: icon, min/max with a range bar scaled to the whole week, rain, gusts."""
    if not days:
        return ""
    lows = [d.get("temperature_2m_min") for d in days if d.get("temperature_2m_min") is not None]
    highs = [d.get("temperature_2m_max") for d in days if d.get("temperature_2m_max") is not None]
    lo, hi = (min(lows), max(highs)) if lows and highs else (0.0, 1.0)
    span = max(hi - lo, 1e-6)
    cards = []
    for i, d in enumerate(days):
        try:
            dt = datetime.fromisoformat(d["date"])
            name = "Today" if i == 0 else dt.strftime("%a")
            sub = dt.strftime("%d %b")
        except (KeyError, ValueError):
            name, sub = d.get("date", ""), ""
        tmin, tmax = d.get("temperature_2m_min"), d.get("temperature_2m_max")
        left = ((tmin - lo) / span * 100) if tmin is not None else 0
        width = (((tmax - tmin) / span) * 100) if tmin is not None and tmax is not None else 0
        sunrise, sunset = _hhmm(d.get("sunrise")), _hhmm(d.get("sunset"))
        cards.append(
            f'<div class="wt-day" title="{escape(analysis.describe_code(d.get("weather_code")))}">'
            f'<div class="d">{_e(name)}</div><div class="dt">{_e(sub)}</div>'
            f'{icons.weather_icon(d.get("weather_code"), True, 48)}'
            f'<div class="kv">{_e(analysis.describe_code(d.get("weather_code")))}</div>'
            f'<div class="tt"><span>{_fmt(tmin)}°</span><b>{_fmt(tmax)}°</b></div>'
            f'<div class="range"><i style="left:{left:.0f}%;width:{max(width, 4):.0f}%"></i></div>'
            f'<div class="kv">💧 {_fmt(d.get("precipitation_probability_max"))}% · {_fmt(d.get("precipitation_sum"), 1)} mm</div>'
            f'<div class="kv">🌬 {_fmt(d.get("wind_speed_10m_max"))} km/h {small_arrow(d.get("wind_direction_10m_dominant"))}'
            f' · gust {_fmt(d.get("wind_gusts_10m_max"))}</div>'
            f'<div class="kv">☀ {sunrise} – {sunset} · UV {_fmt(d.get("uv_index_max"), 1)}</div>'
            "</div>"
        )
    return f'<div class="wt-days">{"".join(cards)}</div>'


def table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], max_rows: int = 500) -> str:
    """Theme-aware HTML table. ``columns`` = [(key, header)]. Values are escaped unless the key
    ends with ``_html`` (pre-rendered, trusted component markup such as status pills)."""
    head = "".join(f"<th>{_e(h)}</th>" for _, h in columns)
    body = []
    for r in rows[:max_rows]:
        cells = []
        for key, _ in columns:
            v = r.get(key)
            if key.endswith("_html"):
                cells.append(f"<td>{v or ''}</td>")
            elif isinstance(v, float):
                cells.append(f"<td>{v:.1f}</td>")
            elif isinstance(v, bool):
                cells.append(f"<td>{'Yes' if v else 'No'}</td>")
            else:
                cells.append(f"<td>{_e('–' if v is None else v)}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return f'<div class="wt-table-wrap"><table class="wt-table"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def report_card(meta: dict[str, Any], tz=None) -> str:
    raw = str(meta.get("created_at", ""))
    try:
        dt = datetime.fromisoformat(raw)
        if tz is not None and dt.tzinfo is not None:
            dt = dt.astimezone(tz)
        zone = dt.strftime("%Z") or ""
        created = f"{dt:%Y-%m-%d %H:%M} {zone if zone and not zone.startswith(('+', '-')) else dt.strftime('%z')}"
    except ValueError:
        created = raw[:16].replace("T", " ")
    extra = []
    if meta.get("city"):
        extra.append(f"📍 {_e(meta['city'])}")
    if meta.get("us_aqi") is not None:
        extra.append(f"AQI {_e(meta['us_aqi'])}")
    if meta.get("model"):
        extra.append(_e(meta["model"]))
    summary = " ".join(str(meta.get("summary", "")).replace("#", "").replace("*", "").split())[:220]
    return (f'<div class="wt-report"><div class="ic">PDF</div><div style="min-width:0">'
            f'<div class="nm">{_e(meta.get("analysis_name") or meta.get("file"))}</div>'
            f'<div class="meta">{status_pill(meta.get("storm_risk") or "Unknown")}<span>🕒 {_e(created)}</span>'
            f'<span>{meta.get("size_kb", 0):.0f} KB</span>{"".join(f"<span>{x}</span>" for x in extra)}</div>'
            + (f'<div class="sum">{_e(summary)}…</div>' if summary else "")
            + "</div></div>")


def empty(message: str) -> str:
    return f'<div class="wt-empty">{_e(message)}</div>'


def footer(company: str = "Neural ThinkPad", product: str = "NeuralCast") -> str:
    return (f'<div class="wt-foot">© {datetime.now().year} {_e(company)} · {_e(product)} · '
            'Weather data by Open-Meteo.com (CC BY 4.0), backup by MET Norway (CC BY 4.0) · Earthquakes by USGS · AI: Google Gemini via LangChain '
            'Deep Agents · Forecasts are probabilistic — follow PMD / NDMA advisories for official warnings.</div>')
