"""Weather-terminal design tokens (dark + light) and the global CSS built from them.

The theme is chosen per browser session (``?theme=light``), never via Streamlit's global
config, so one visitor's choice cannot change another's.
"""

from __future__ import annotations

from dataclasses import dataclass

# Status palette (reserved for risk / AQI state; always paired with a text label)
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
RISK_STATUS = {"Low": "good", "Moderate": "warning", "High": "serious", "Severe": "critical"}
AQI_STATUS = {"Good": "good", "Moderate": "warning", "Unhealthy for sensitive groups": "serious",
              "Unhealthy": "critical", "Very unhealthy": "critical", "Hazardous": "critical"}


@dataclass(frozen=True)
class Palette:
    mode: str
    page: str
    surface: str
    surface_2: str
    border: str
    ink: str
    ink_2: str
    muted: str
    accent: str
    grid: str
    axis: str
    # categorical series (validated per mode with the dataviz validator)
    blue: str
    orange: str
    aqua: str
    # sequential ramps, near-zero step first (recedes toward the surface)
    seq_blue: tuple[str, ...]
    seq_orange: tuple[str, ...]


DARK = Palette(
    mode="dark", page="#0a0f1a", surface="#121a29", surface_2="#18223a", border="rgba(148,163,184,0.16)",
    ink="#eef2f8", ink_2="#b6c2d4", muted="#8291a7", accent="#38bdf8", grid="#223049", axis="#33425c",
    blue="#3987e5", orange="#d95926", aqua="#199e70",
    seq_blue=("#1b2537", "#184f95", "#2a78d6", "#5598e7", "#9ec5f4"),
    seq_orange=("#2a1f1c", "#7a3417", "#b4441b", "#d95926", "#f19a72"),
)
LIGHT = Palette(
    mode="light", page="#f3f6fb", surface="#ffffff", surface_2="#eef3fa", border="rgba(15,23,42,0.10)",
    ink="#0b1220", ink_2="#44526a", muted="#66738a", accent="#0284c7", grid="#e5eaf2", axis="#c7d0dd",
    blue="#2a78d6", orange="#eb6834", aqua="#1baf7a",
    seq_blue=("#eef4fc", "#cde2fb", "#86b6ef", "#3987e5", "#184f95"),
    seq_orange=("#fdf1ea", "#f9c9b3", "#f19a72", "#eb6834", "#b4441b"),
)


def palette(mode: str) -> Palette:
    return LIGHT if mode == "light" else DARK


def risk_color(level: str) -> str:
    return STATUS.get(RISK_STATUS.get(level, ""), "#8291a7")


def aqi_color(category: str) -> str:
    return STATUS.get(AQI_STATUS.get(category, ""), "#8291a7")


def build_css(mode: str = "dark") -> str:
    p = palette(mode)
    light = mode == "light"
    bg_glow = ("radial-gradient(1200px 500px at 10% -10%, rgba(2,132,199,.10), transparent 60%),"
               "radial-gradient(900px 400px at 100% 0%, rgba(99,102,241,.08), transparent 60%)") if light else (
               "radial-gradient(1200px 500px at 10% -10%, rgba(56,189,248,.08), transparent 60%),"
               "radial-gradient(900px 400px at 100% 0%, rgba(124,58,237,.07), transparent 60%)")
    shadow = "0 1px 2px rgba(15,23,42,.06), 0 4px 16px rgba(15,23,42,.05)" if light else "none"
    tab_sel = "linear-gradient(180deg,#e0f2fe,#f0f9ff)" if light else "linear-gradient(180deg,#1f2c47,#19243b)"
    hour_now = "linear-gradient(180deg,#e0f2fe,#ffffff)" if light else "linear-gradient(180deg,#1b2a48,#121a29)"
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');

:root {{
  --page:{p.page}; --surface:{p.surface}; --surface-2:{p.surface_2}; --border:{p.border};
  --ink:{p.ink}; --ink-2:{p.ink_2}; --muted:{p.muted}; --accent:{p.accent}; --shadow:{shadow};
  --good:{STATUS['good']}; --warning:{STATUS['warning']}; --serious:{STATUS['serious']}; --critical:{STATUS['critical']};
  --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  --sans: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
  color-scheme: {mode};
}}

/* ---------- app chrome ---------- */
html, body, .stApp {{ background: var(--page) !important; color: var(--ink); font-family: var(--sans); }}
[data-testid="stAppViewContainer"] {{ background: {bg_glow}, var(--page) !important; }}
[data-testid="stHeader"] {{ background: transparent !important; }}
/* hide only Deploy + main menu; the sidebar re-open button must stay reachable */
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"], footer, [data-testid="stDecoration"] {{ display: none !important; }}
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapseButton"] button {{
  background: var(--surface) !important; border: 1px solid var(--border) !important; border-radius: 10px !important;
  color: var(--ink) !important; box-shadow: var(--shadow);
}}
[data-testid="stExpandSidebarButton"] svg, [data-testid="stSidebarCollapseButton"] svg {{ color: var(--accent) !important; fill: var(--accent) !important; }}
.block-container {{ padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1480px; }}
[data-testid="stSidebar"] {{ background: var(--surface) !important; border-right: 1px solid var(--border); }}
h1, h2, h3, h4, h5 {{ font-family: var(--sans); letter-spacing: -0.01em; color: var(--ink) !important; }}

/* native widgets follow the active palette */
.stApp p, .stApp li, .stApp label, [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p,
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"], [data-testid="stSidebar"] * {{ color: var(--ink); }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{ color: var(--muted) !important; }}
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"], [data-baseweb="select"] > div,
[data-testid$="RootElement"], [data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"],
[data-testid="stChatInputTextArea"], [data-testid="stNumberInputContainer"] {{
  background: var(--surface) !important; border-color: var(--border) !important; border-radius: 10px !important;
}}
[data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"], [data-testid$="RootElement"] {{
  border: 1px solid var(--border) !important; box-shadow: var(--shadow);
}}
.stApp input, .stApp textarea, [data-baseweb="select"] *, [data-testid="stSelectbox"] *, [data-testid="stMultiSelect"] * {{
  color: var(--ink) !important; -webkit-text-fill-color: var(--ink);
}}
[role="listbox"], [role="option"] {{ background: var(--surface) !important; color: var(--ink) !important; }}
[role="option"]:hover, [role="option"][aria-selected="true"] {{ background: var(--surface-2) !important; }}
[data-testid="stPills"] button, [data-testid="stButtonGroup"] button {{
  background: var(--surface) !important; border-color: var(--border) !important;
}}
[data-testid="stPills"] button p, [data-testid="stButtonGroup"] button p {{ color: var(--ink-2) !important; }}
[data-testid="stButtonGroup"] button[kind$="Active"], [data-testid="stPills"] button[kind$="Active"] {{
  background: {p.accent}22 !important; border-color: {p.accent} !important;
}}
[data-testid="stButtonGroup"] button[kind$="Active"] p, [data-testid="stPills"] button[kind$="Active"] p {{ color: var(--ink) !important; font-weight: 700; }}
.stApp input::placeholder, .stApp textarea::placeholder {{ color: var(--muted) !important; -webkit-text-fill-color: var(--muted); }}
[data-baseweb="popover"] ul, [data-baseweb="menu"], [data-baseweb="popover"] li {{ background: var(--surface) !important; color: var(--ink) !important; }}
[data-baseweb="popover"] li:hover, [data-baseweb="popover"] [aria-selected="true"] {{ background: var(--surface-2) !important; }}
[data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"], [data-testid="stSliderThumbValue"] {{ color: var(--ink-2) !important; }}
[data-testid="stChatInput"], [data-testid="stChatInput"] > div {{ background: var(--surface) !important; border-color: var(--border) !important; border-radius: 14px; }}
[data-testid="stChatMessage"] {{ background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 14px 16px; box-shadow: var(--shadow); }}
[data-testid="stExpander"] details, [data-testid="stExpander"] summary {{ background: var(--surface) !important; border-color: var(--border) !important; border-radius: 14px; color: var(--ink) !important; }}
[data-testid="stExpander"] summary * {{ color: var(--ink) !important; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-color: var(--border) !important; border-radius: 16px !important; }}
[data-testid="stAlert"] {{ border-radius: 12px; }}
[data-testid="stAlert"] p, [data-testid="stAlert"] div, [data-testid="stAlert"] code {{ color: var(--ink) !important; }}
[data-testid="stCode"] pre, .stApp code {{ background: var(--surface-2) !important; color: var(--ink) !important; }}
[data-testid="stVegaLiteChart"] {{ background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 10px 8px 4px; box-shadow: var(--shadow); }}
[data-testid="stDeckGlJsonChart"] {{ border-radius: 18px; overflow: hidden; border: 1px solid var(--border); }}
[data-testid="stToggle"] label p {{ color: var(--ink) !important; font-weight: 600; }}

/* main navigation: tabs as a full-width segmented bar */
[data-testid="stTabs"] [role="tablist"] {{
  display: flex; gap: 6px; background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 6px;
  overflow-x: auto; box-shadow: var(--shadow); margin-bottom: 6px;
}}
[data-testid="stTabs"] [role="tablist"]::after, [data-testid="stTabs"] [role="tablist"] + div:empty {{ display: none; }}
[data-testid="stTab"] {{
  flex: 1 1 0; min-width: max-content; height: 46px; padding: 0 18px; border-radius: 12px; justify-content: center;
  background: transparent; border: 1px solid transparent; transition: background .15s ease, border-color .15s ease;
}}
[data-testid="stTab"] p {{ color: var(--ink-2) !important; font-weight: 600 !important; font-size: .95rem !important; white-space: nowrap; }}
[data-testid="stTab"]:hover {{ background: var(--surface-2); }}
[data-testid="stTab"][aria-selected="true"] {{ background: {tab_sel}; border-color: {p.accent}88; box-shadow: 0 2px 10px {p.accent}22; }}
[data-testid="stTab"][aria-selected="true"] p {{ color: var(--ink) !important; font-weight: 700 !important; }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"], [data-testid="stTabs"] [data-baseweb="tab-border"] {{ display: none !important; }}

/* search console (command bar) */
.st-key-cmdbar {{
  background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 14px 18px 10px;
  box-shadow: var(--shadow); margin: 10px 0 12px;
}}
.st-key-cmdbar [data-testid="stWidgetLabel"] p {{ font-family: var(--mono); font-size: .7rem !important; letter-spacing: .1em;
  text-transform: uppercase; color: var(--muted) !important; }}
.st-key-cmdbar [data-testid$="RootElement"], .st-key-cmdbar [data-testid="stSelectbox"] [role="group"] {{
  min-height: 46px; border-radius: 12px !important; background: var(--surface-2) !important;
}}
.st-key-cmdbar input {{ font-size: .95rem !important; }}
.st-key-cmdbar [data-testid$="RootElement"]:focus-within, .st-key-cmdbar [role="group"]:focus-within {{
  border-color: var(--accent) !important; box-shadow: 0 0 0 3px {p.accent}33 !important;
}}
.wt-clock {{ color: var(--ink) !important; font-weight: 600; }}

/* header card (full width) with the sun/moon theme icon in its corner */
.st-key-head {{ position: relative; background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
  box-shadow: var(--shadow); padding: 2px 4px; gap: 0 !important; }}
.st-key-head .wt-topbar {{ background: transparent; border: 0; box-shadow: none; padding-right: 70px; }}
.st-key-theme_btn {{ position: absolute !important; top: 12px; right: 14px; z-index: 5; width: auto !important; }}
.st-key-theme_btn button {{ width: 44px; height: 44px; min-height: 44px; border-radius: 50% !important; padding: 0 !important;
  font-size: 1.25rem; background: var(--surface-2) !important; border: 1px solid var(--border) !important;
  box-shadow: var(--shadow); justify-content: center; }}
.st-key-theme_btn button:hover {{ border-color: var(--accent) !important; transform: rotate(-15deg) scale(1.06); }}

/* search console wraps instead of squeezing on narrow screens */
.st-key-cmdbar [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap !important; row-gap: 10px; }}
.st-key-cmdbar [data-testid="stColumn"] {{ flex: 1 1 210px !important; min-width: min(210px, 100%) !important; }}
.st-key-cmdbar [data-testid="stColumn"]:last-child {{ flex: 1 1 140px !important; min-width: 140px !important; }}
.stMain, [data-testid="stMain"] {{ overflow-x: hidden; }}

/* alerts follow the active theme (Streamlit's base theme paints them dark) */
[data-testid="stAlertContainer"] {{ background: var(--surface-2) !important; border: 1px solid var(--border); }}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {{ background: rgba(12,163,12,.12) !important; border-color: rgba(12,163,12,.35); }}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {{ background: rgba(208,59,59,.12) !important; border-color: rgba(208,59,59,.35); }}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {{ background: rgba(250,178,25,.14) !important; border-color: rgba(250,178,25,.4); }}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {{ background: {p.accent}18 !important; border-color: {p.accent}55; }}

/* buttons */
.stButton > button, .stDownloadButton > button {{
  border-radius: 10px; border: 1px solid var(--border); background: var(--surface-2); color: var(--ink);
  font-weight: 600; transition: all .15s ease;
}}
.stButton > button p, .stDownloadButton > button p {{ color: var(--ink) !important; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color: var(--accent); transform: translateY(-1px); }}
.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, #0ea5e9, #6366f1); border: 0; }}
.stButton > button[kind="primary"] p {{ color: #fff !important; }}

/* ---------- terminal components ---------- */
.wt-topbar {{ display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap;
  padding: 12px 18px; background: var(--surface); border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--shadow); }}
.wt-brand {{ display:flex; align-items:center; gap:12px; }}
.wt-brand .name {{ font-weight: 800; font-size: 1.15rem; letter-spacing: .02em; color: var(--ink); }}
.wt-brand .name b {{ color: var(--accent); }}
.wt-brand .sub {{ font-family: var(--mono); font-size: .72rem; color: var(--muted); letter-spacing: .08em; text-transform: uppercase; }}
.wt-pills {{ display:flex; gap:8px; flex-wrap:wrap; }}
.wt-pill {{ display:inline-flex; align-items:center; gap:7px; padding: 5px 11px; border-radius: 999px; font-family: var(--mono);
  font-size: .72rem; letter-spacing: .04em; color: var(--ink-2); background: var(--surface-2); border: 1px solid var(--border); }}
.wt-dot {{ width:8px; height:8px; border-radius:50%; background: var(--muted); }}
.wt-dot.on {{ background: var(--good); box-shadow: 0 0 0 3px rgba(12,163,12,.18); animation: wt-pulse 2.4s infinite; }}
.wt-dot.off {{ background: #94a3b8; }}

.wt-label {{ font-family: var(--mono); font-size: .7rem; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }}
.wt-section {{ display:flex; align-items:baseline; gap:12px; margin: 26px 0 12px; flex-wrap: wrap; }}
.wt-section h3 {{ margin:0; font-size: 1.12rem; font-weight: 700; color: var(--ink); }}
.wt-section span {{ font-family: var(--mono); font-size: .72rem; color: var(--muted); letter-spacing: .08em; text-transform: uppercase; }}

/* hero keeps its weather-mood gradient (white text) in both themes */
.wt-hero {{ position:relative; overflow:hidden; border-radius: 22px; border: 1px solid var(--border); padding: 26px 28px; color: #eef2f8;
  display:grid; grid-template-columns: minmax(0,1.35fr) minmax(0,1fr); gap: 22px; box-shadow: var(--shadow); }}
.wt-hero::after {{ content:""; position:absolute; inset:0; background: linear-gradient(180deg, transparent 40%, rgba(2,6,23,.45)); pointer-events:none; }}
.wt-hero > * {{ position:relative; z-index:1; }}
.wt-hero .wt-label {{ color: rgba(238,242,248,.78); }}
.wt-place {{ font-size: 1.9rem; font-weight: 800; line-height: 1.1; color: #fff; }}
.wt-region {{ color: rgba(238,242,248,.8); font-size: .95rem; margin-top: 4px; }}
.wt-now {{ display:flex; align-items:center; gap: 18px; margin-top: 16px; }}
.wt-temp {{ font-size: 4.6rem; font-weight: 800; line-height: 1; letter-spacing: -0.04em; color: #fff; }}
.wt-temp sup {{ font-size: 1.6rem; font-weight: 600; vertical-align: top; margin-left: 2px; color: rgba(238,242,248,.8); }}
.wt-cond {{ font-size: 1.15rem; font-weight: 600; color: #fff; }}
.wt-meta {{ display:flex; gap: 18px; flex-wrap: wrap; margin-top: 14px; color: rgba(238,242,248,.82); font-size: .9rem; }}
.wt-meta b {{ color: #fff; font-weight: 600; }}
.wt-risk {{ background: rgba(2,6,23,.45); border: 1px solid rgba(255,255,255,.12); border-radius: 18px; padding: 16px 18px; backdrop-filter: blur(6px); }}
.wt-facts {{ display:grid; grid-template-columns: 1fr 1fr; gap: 10px 16px; margin-top: 10px; }}
.wt-fact .v {{ font-weight: 700; font-size: 1rem; color: #fff; }}
.wt-fact .k {{ font-size: .76rem; color: rgba(238,242,248,.7); }}

.wt-status {{ display:inline-flex; align-items:center; gap:6px; padding: 3px 10px; border-radius: 999px; font-weight: 700;
  font-size: .75rem; letter-spacing: .03em; color: #fff; white-space: nowrap; }}
.wt-status.warning {{ color: #0b0b0b; }}

/* tiles */
.wt-tiles {{ display:grid; grid-template-columns: repeat(7, minmax(0,1fr)); gap: 12px; margin-top: 14px; }}
.wt-tile.wide {{ grid-column: span 2; }}
.wt-tile {{ background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 14px 16px; min-height: 150px;
  display:flex; flex-direction:column; gap: 6px; transition: border-color .2s ease, transform .2s ease; box-shadow: var(--shadow); color: var(--ink); }}
.wt-tile:hover {{ border-color: {p.accent}88; transform: translateY(-2px); }}
.wt-tile .head {{ display:flex; align-items:center; justify-content:space-between; gap: 6px; }}
.wt-tile .big {{ font-size: 1.7rem; font-weight: 800; letter-spacing: -0.02em; }}
.wt-tile .big small {{ font-size: .85rem; font-weight: 600; color: var(--ink-2); margin-left: 3px; }}
.wt-tile .note {{ font-size: .8rem; color: var(--ink-2); }}
.wt-bar {{ height: 6px; border-radius: 999px; background: var(--surface-2); overflow:hidden; margin-top: auto; }}
.wt-bar > i {{ display:block; height:100%; border-radius: 999px; }}

/* hourly strip & 7-day cards */
.wt-strip {{ display:flex; gap: 10px; overflow-x: auto; padding: 4px 2px 10px; scroll-snap-type: x mandatory; }}
.wt-strip::-webkit-scrollbar {{ height: 8px; }}
.wt-strip::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 8px; }}
.wt-hour {{ flex: 0 0 96px; scroll-snap-align: start; background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
  padding: 10px 8px 12px; display:flex; flex-direction:column; align-items:center; gap: 4px; color: var(--ink); box-shadow: var(--shadow); }}
.wt-hour.now {{ background: {hour_now}; border-color: {p.accent}77; }}
.wt-hour .t {{ font-family: var(--mono); font-size: .75rem; color: var(--muted); }}
.wt-hour .temp {{ font-weight: 800; font-size: 1.05rem; }}
.wt-hour .pop {{ font-size: .75rem; color: {p.blue}; font-weight: 600; }}
.wt-hour .wind {{ font-size: .72rem; color: var(--ink-2); display:flex; align-items:center; gap: 3px; }}
.wt-hour .flag {{ width: 100%; height: 4px; border-radius: 999px; margin-top: 4px; }}
.wt-days {{ display:grid; grid-template-columns: repeat(7, minmax(0,1fr)); gap: 10px; }}
.wt-day {{ background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 12px; display:flex; flex-direction:column;
  align-items:center; gap: 5px; color: var(--ink); box-shadow: var(--shadow); text-align:center; }}
.wt-day .d {{ font-weight: 700; }}
.wt-day .dt {{ font-family: var(--mono); font-size: .7rem; color: var(--muted); }}
.wt-day .range {{ width: 100%; height: 6px; border-radius: 999px; background: var(--surface-2); position: relative; margin: 4px 0; }}
.wt-day .range > i {{ position:absolute; top:0; bottom:0; border-radius: 999px; background: linear-gradient(90deg, {p.blue}, {p.orange}); }}
.wt-day .tt {{ display:flex; justify-content:space-between; width:100%; font-size: .85rem; }}
.wt-day .tt b {{ font-weight: 800; }}
.wt-day .tt span {{ color: var(--ink-2); }}
.wt-day .kv {{ font-size: .74rem; color: var(--ink-2); }}

/* city cards, KPIs, tables, reports */
.wt-grid {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 12px; }}
.wt-city {{ background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 14px 16px; display:flex; flex-direction:column; gap: 8px; color: var(--ink); box-shadow: var(--shadow); }}
.wt-city .row {{ display:flex; align-items:center; justify-content:space-between; gap: 8px; }}
.wt-city .nm {{ font-weight: 700; font-size: 1rem; }}
.wt-city .pr {{ font-size: .74rem; color: var(--muted); }}
.wt-city .tp {{ font-weight: 800; font-size: 1.5rem; }}
.wt-city .kv {{ font-size: .78rem; color: var(--ink-2); display:flex; gap: 10px; flex-wrap: wrap; }}
.wt-kpis {{ display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; margin: 6px 0 14px; }}
.wt-kpi {{ background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 14px 16px; color: var(--ink); box-shadow: var(--shadow); }}
.wt-kpi .v {{ font-size: 1.8rem; font-weight: 800; margin-top: 4px; }}
.wt-kpi .s {{ font-size: .8rem; color: var(--ink-2); }}
.wt-table-wrap {{ overflow-x:auto; border: 1px solid var(--border); border-radius: 16px; background: var(--surface); box-shadow: var(--shadow); }}
.wt-table {{ width:100%; border-collapse: collapse; font-size: .84rem; color: var(--ink); }}
.wt-table th {{ text-align:left; font-family: var(--mono); font-size: .68rem; letter-spacing: .08em; text-transform: uppercase; color: var(--muted);
  padding: 10px 12px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface); white-space: nowrap; }}
.wt-table td {{ padding: 9px 12px; border-bottom: 1px solid var(--border); white-space: nowrap; font-variant-numeric: tabular-nums; }}
.wt-table tr:last-child td {{ border-bottom: 0; }}
.wt-table tr:hover td {{ background: var(--surface-2); }}
.wt-report {{ display:flex; align-items:center; gap: 14px; color: var(--ink); }}
.wt-report .ic {{ width: 44px; height: 52px; border-radius: 8px; background: linear-gradient(160deg, #ef4444, #b91c1c); color:#fff;
  font-family: var(--mono); font-size: .7rem; font-weight: 700; display:flex; align-items:flex-end; justify-content:center; padding-bottom: 6px; flex-shrink: 0; }}
.wt-report .nm {{ font-weight: 700; }}
.wt-report .meta {{ font-size: .78rem; color: var(--muted); font-family: var(--mono); display:flex; gap: 10px; flex-wrap: wrap; align-items:center; }}
.wt-report .sum {{ font-size: .82rem; color: var(--ink-2); margin-top: 4px; }}
.wt-empty {{ text-align:center; padding: 40px 20px; color: var(--ink-2); background: var(--surface); border: 1px dashed var(--border); border-radius: 18px; }}
.wt-foot {{ margin-top: 36px; padding-top: 14px; border-top: 1px solid var(--border); color: var(--muted); font-size: .78rem; font-family: var(--mono); }}

/* ---------- enterprise sidebar ---------- */
[data-testid="stSidebar"] {{ background: {"linear-gradient(180deg,#ffffff,#f3f6fb)" if light else "linear-gradient(180deg,#0e1626,#0a0f1a)"} !important; }}
[data-testid="stSidebar"] .block-container, [data-testid="stSidebarUserContent"] {{ padding-top: .6rem; }}
.nt-brand {{ display:flex; align-items:center; gap: 12px; padding: 6px 2px 14px; border-bottom: 1px solid var(--border); }}
.nt-logo {{ width: 46px; height: 46px; border-radius: 14px; display:flex; align-items:center; justify-content:center;
  background: linear-gradient(135deg, #0ea5e9, #6366f1); box-shadow: 0 6px 18px rgba(99,102,241,.35); flex-shrink: 0; }}
.nt-company {{ font-weight: 800; font-size: 1.02rem; letter-spacing: .01em; color: var(--ink); }}
.nt-product {{ font-weight: 700; font-size: .86rem; color: var(--accent); }}
.nt-tag {{ font-size: .7rem; color: var(--muted); }}
.nt-user {{ display:flex; align-items:center; gap: 10px; margin: 12px 0 6px; padding: 10px 12px; border-radius: 14px;
  background: var(--surface-2); border: 1px solid var(--border); position: relative; }}
.nt-avatar {{ width: 36px; height: 36px; border-radius: 50%; display:flex; align-items:center; justify-content:center; font-weight: 800;
  font-size: .85rem; color: #fff; background: linear-gradient(135deg, #f59e0b, #ef4444); flex-shrink: 0; }}
.nt-name {{ font-weight: 700; font-size: .9rem; color: var(--ink); }}
.nt-role {{ font-size: .72rem; color: var(--muted); }}
.nt-online {{ position:absolute; right: 12px; top: 50%; width: 8px; height: 8px; margin-top: -4px; border-radius: 50%; background: var(--good); }}
.nt-side-h {{ font-family: var(--mono); font-size: .66rem; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); margin: 16px 2px 6px; }}
[data-testid="stSidebar"] .stButton > button {{ justify-content: flex-start; text-align: left; padding: 8px 12px; font-weight: 600; }}
[data-testid="stSidebar"] .stButton > button p {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }}
/* "New conversation" = the one primary action */
[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
  justify-content: center; background: linear-gradient(135deg, #0ea5e9, #6366f1) !important; border: 0 !important;
  box-shadow: 0 6px 16px rgba(99,102,241,.30); height: 44px;
}}
[data-testid="stSidebar"] .stButton > button[kind="primary"] p {{ color: #fff !important; }}
/* history rows: plain list items; the open chat is highlighted */
[data-testid="stSidebar"] .stButton > button[kind="tertiary"] {{
  width: 100%; border-radius: 10px; padding: 8px 12px; background: transparent; border: 1px solid transparent;
}}
[data-testid="stSidebar"] .stButton > button[kind="tertiary"] p {{ color: var(--ink-2) !important; font-weight: 500; }}
[data-testid="stSidebar"] .stButton > button[kind="tertiary"]:hover {{ background: var(--surface-2); }}
[data-testid="stSidebar"] [class*="st-key-conv-"] button[kind="secondary"] {{
  background: {p.accent}1f !important; border: 1px solid {p.accent}88 !important; border-radius: 10px;
}}
[data-testid="stSidebar"] [class*="st-key-conv-"] button[kind="secondary"] p {{ color: var(--ink) !important; font-weight: 600; }}

/* configuration panel */
.nt-key {{ display:flex; gap: 10px; align-items:flex-start; padding: 10px 12px; border-radius: 12px; margin-bottom: 8px;
  border: 1px solid var(--border); background: var(--surface); }}
.nt-key.ok {{ border-color: rgba(12,163,12,.45); background: rgba(12,163,12,.08); }}
.nt-key.bad {{ border-color: rgba(208,59,59,.5); background: rgba(208,59,59,.08); }}
.nt-key-ic {{ font-size: 1.05rem; line-height: 1.3; }}
.nt-key-t {{ font-weight: 700; font-size: .86rem; color: var(--ink); }}
.nt-key-d {{ font-size: .76rem; color: var(--ink-2); line-height: 1.35; }}
.nt-key-d code {{ font-size: .72rem; padding: 0 4px; border-radius: 4px; }}
.nt-st {{ display:flex; flex-direction:column; gap: 2px; }}
.nt-st-row {{ display:flex; gap: 10px; align-items:flex-start; padding: 7px 2px; border-bottom: 1px solid var(--border); }}
.nt-st-row:last-child {{ border-bottom: 0; }}
.nt-dot {{ width: 9px; height: 9px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; background: #94a3b8; }}
.nt-dot.on {{ background: var(--good); box-shadow: 0 0 0 3px rgba(12,163,12,.15); }}
.nt-st-name {{ font-size: .84rem; font-weight: 600; color: var(--ink); }}
.nt-st-note {{ font-size: .74rem; color: var(--muted); word-break: break-word; }}
[data-testid="stSidebar"] [data-testid="stExpander"] details {{ background: var(--surface-2) !important; }}

/* live context card (AI tab) */
.fc {{ background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 16px 18px; box-shadow: var(--shadow); color: var(--ink); }}
.fc-head {{ display:flex; justify-content:space-between; align-items:center; gap: 10px; margin-bottom: 8px; }}
.fc-city {{ font-size: 1.4rem; font-weight: 800; }}
.fc-sub {{ font-size: .76rem; color: var(--muted); }}
.fc-row {{ display:flex; justify-content:space-between; gap: 12px; padding: 8px 0; border-top: 1px solid var(--border); font-size: .84rem; align-items:center; }}
.fc-row span {{ color: var(--muted); white-space: nowrap; }}
.fc-row b {{ font-weight: 600; text-align: right; display:flex; gap: 6px; align-items:center; flex-wrap: wrap; justify-content:flex-end; }}

/* icons are SVG images that carry their own animation CSS (see ui/icons.py) */
.wx-icon, .wt-gauge, .wt-compass {{ display:block; flex-shrink:0; }}
.wt-arrow {{ display:inline-block; vertical-align:middle; }}
@keyframes wt-pulse {{ 0%,100% {{ box-shadow: 0 0 0 3px rgba(12,163,12,.18); }} 50% {{ box-shadow: 0 0 0 6px rgba(12,163,12,.05); }} }}
@media (prefers-reduced-motion: reduce) {{ .wt-dot.on {{ animation: none !important; }} }}

/* ---------- responsive ---------- */
@media (max-width: 1200px) {{ .wt-tiles {{ grid-template-columns: repeat(4, minmax(0,1fr)); }} .wt-days {{ grid-template-columns: repeat(4, minmax(0,1fr)); }} }}
@media (max-width: 900px) {{
  .wt-hero {{ grid-template-columns: 1fr; padding: 20px; }}
  .wt-temp {{ font-size: 3.6rem; }}
  .wt-kpis {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}
}}
@media (max-width: 640px) {{
  .block-container {{ padding: 3.4rem .7rem 2rem !important; }}  /* room for the » sidebar button */
  .st-key-head .wt-topbar {{ padding: 10px 56px 10px 10px; }}
  .st-key-theme_btn {{ top: 10px; right: 10px; }}
  .wt-brand .name {{ font-size: 1rem; }}
  .wt-brand .sub {{ font-size: .62rem; }}
  .wt-pill {{ font-size: .62rem; padding: 4px 8px; }}
  .st-key-cmdbar {{ padding: 10px 12px 6px; }}
  [data-testid="stTab"] {{ height: 40px; padding: 0 12px; flex: 0 0 auto; }}
  [data-testid="stTab"] p {{ font-size: .85rem !important; }}
  .wt-hero {{ padding: 16px; gap: 14px; border-radius: 18px; }}
  .wt-temp {{ font-size: 3rem; }}
  .wt-now img.wx-icon {{ width: 84px; height: 84px; }}
  .wt-risk {{ padding: 12px; }}
  .wt-tile {{ min-height: 0; padding: 12px; }}
  .wt-tile.wide {{ grid-column: span 2; }}
  .wt-hour {{ flex-basis: 80px; }}
  .wt-kpi .v {{ font-size: 1.4rem; }}
  .wt-section {{ margin: 18px 0 10px; }}
  .fc-row {{ font-size: .8rem; }}
  [data-testid="stChatMessage"] {{ padding: 10px 12px; }}
}}
@media (max-width: 560px) {{
  .wt-tiles, .wt-days {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}
  .wt-place {{ font-size: 1.5rem; }}
  .wt-kpis {{ grid-template-columns: 1fr 1fr; gap: 8px; }}
  .wt-grid {{ grid-template-columns: 1fr 1fr; }}
}}
@media (max-width: 380px) {{ .wt-grid {{ grid-template-columns: 1fr; }} }}
</style>
"""


CSS = build_css("dark")  # backwards-compatible default
