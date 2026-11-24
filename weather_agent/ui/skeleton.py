"""First-paint loading screen: a themed skeleton of the portal plus a loading card.

Streamlit draws widgets one by one while the script runs (and before custom styles and live data
arrive), which looks broken for a moment. ``overlay()`` is drawn first and covers that; ``ready()`` is
drawn last and its presence fades the overlay out (CSS ``body:has(.nc-ready)``). On later reruns the
previous ``ready`` marker is still on the page, so the overlay never flashes again. A CSS fail-safe
hides it after 40 s even if the script stops early.
"""

from __future__ import annotations

from html import escape

from . import icons


def _bars(n: int, cls: str) -> str:
    return "".join(f'<div class="sk {cls}"></div>' for _ in range(n))


def overlay(product: str, company: str, city: str) -> str:
    side = (
        '<aside class="nc-sk-side">'
        '<div class="nc-sk-row"><div class="sk sk-logo"></div><div class="nc-sk-col">'
        '<div class="sk sk-line w70"></div><div class="sk sk-line w45"></div></div></div>'
        '<div class="sk sk-card h56"></div>'
        '<div class="sk sk-line w30 mt"></div><div class="sk sk-input"></div>'
        '<div class="sk sk-btn"></div>'
        '<div class="sk sk-line w40 mt"></div><div class="sk sk-input"></div>'
        '<div class="sk sk-line w45 mt"></div>' + _bars(3, "sk-line w90") +
        '</aside>'
    )
    main = (
        '<main class="nc-sk-main">'
        '<div class="nc-sk-card nc-sk-head"><div class="sk sk-logo"></div><div class="nc-sk-col grow">'
        '<div class="sk sk-line w40"></div><div class="sk sk-line w60 thin"></div>'
        f'<div class="nc-sk-pills">{_bars(6, "sk-pill")}</div></div><div class="sk sk-round"></div></div>'
        f'<div class="nc-sk-card nc-sk-search">{_bars(4, "sk-input")}</div>'
        f'<div class="nc-sk-card nc-sk-tabs">{_bars(6, "sk-tab")}</div>'
        '<div class="nc-sk-hero"><div class="nc-sk-col grow"><div class="sk sk-line w30 on-dark"></div>'
        '<div class="sk sk-line w45 tall on-dark"></div><div class="nc-sk-row">'
        '<div class="sk sk-sun on-dark"></div><div class="sk sk-temp on-dark"></div></div></div>'
        '<div class="sk sk-panel on-dark"></div></div>'
        f'<div class="nc-sk-tiles">{_bars(6, "sk-tile")}</div>'
        f'<div class="nc-sk-strip">{_bars(10, "sk-hour")}</div>'
        '</main>'
    )
    steps = ("Connecting to live weather (Open-Meteo)…", "Fetching air quality & earthquakes (USGS)…",
             f"Preparing the dashboard for {city}…")
    loader = (
        '<div class="nc-loader" role="status" aria-live="polite">'
        f'<div class="nc-loader-logo">{icons.weather_icon(95, True, 44)}</div>'
        f'<div class="nc-loader-t">{escape(product)}</div>'
        f'<div class="nc-loader-s">by {escape(company)}</div>'
        '<div class="nc-loader-steps">'
        + "".join(f'<span style="animation-delay:{i * 1.6:.1f}s">{escape(s)}</span>' for i, s in enumerate(steps))
        + '</div><div class="nc-loader-bar"><i></i></div></div>'
    )
    return (f'<div class="nc-boot" aria-label="Loading {escape(product)}">'
            f'<div class="nc-sk-layout">{side}{main}</div>{loader}</div>')


def ready() -> str:
    """Marker drawn at the very end of the page: its presence fades the loading screen out."""
    return '<div class="nc-ready" aria-hidden="true"></div>'


def css(p, light: bool) -> str:
    """Styles for the loading screen (included by ``theme.build_css``; f-string, braces doubled)."""
    return f"""
/* ---------- first-paint loading screen (ui/skeleton.py) ---------- */
.nc-boot {{ position: fixed; inset: 0; z-index: 1000000; background: var(--page); overflow: hidden;
  transition: opacity .45s ease, visibility .45s ease; animation: nc-failsafe .4s ease 40s forwards; }}
body:has(.nc-ready) .nc-boot {{ opacity: 0; visibility: hidden; pointer-events: none; }}
@keyframes nc-failsafe {{ to {{ opacity: 0; visibility: hidden; pointer-events: none; }} }}
.nc-ready {{ display: none; }}
.nc-sk-layout {{ display: flex; height: 100%; }}
.nc-sk-side {{ width: 300px; flex-shrink: 0; padding: 26px 20px; border-right: 1px solid var(--border); background: var(--surface);
  display: flex; flex-direction: column; gap: 12px; }}
.nc-sk-main {{ flex: 1; max-width: 1480px; margin: 0 auto; padding: 22px 32px; display: flex; flex-direction: column; gap: 14px; overflow: hidden; }}
.nc-sk-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 16px 18px; box-shadow: var(--shadow); }}
.nc-sk-row {{ display: flex; align-items: center; gap: 12px; }}
.nc-sk-col {{ display: flex; flex-direction: column; gap: 8px; }}
.nc-sk-col.grow {{ flex: 1; }}
.nc-sk-head {{ display: flex; align-items: center; gap: 14px; }}
.nc-sk-pills {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }}
.nc-sk-search {{ display: grid; grid-template-columns: 1.5fr 1.5fr 1fr .7fr; gap: 14px; }}
.nc-sk-tabs {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; padding: 8px; }}
.nc-sk-hero {{ display: flex; gap: 22px; border-radius: 22px; padding: 26px 28px; min-height: 230px;
  background: linear-gradient(135deg, #1e3a5f, #0d1526 70%); }}
.nc-sk-tiles {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }}
.nc-sk-strip {{ display: flex; gap: 10px; }}
.sk {{ border-radius: 10px; background: linear-gradient(90deg, var(--surface-2) 25%, {p.accent}22 37%, var(--surface-2) 63%);
  background-size: 400% 100%; animation: sk-shimmer 1.4s ease-in-out infinite; }}
.sk.on-dark {{ background: linear-gradient(90deg, rgba(255,255,255,.08) 25%, rgba(255,255,255,.18) 37%, rgba(255,255,255,.08) 63%);
  background-size: 400% 100%; }}
@keyframes sk-shimmer {{ 0% {{ background-position: 100% 50%; }} 100% {{ background-position: 0 50%; }} }}
.sk-logo {{ width: 46px; height: 46px; border-radius: 14px; flex-shrink: 0; }}
.sk-round {{ width: 44px; height: 44px; border-radius: 50%; flex-shrink: 0; }}
.sk-line {{ height: 12px; }} .sk-line.thin {{ height: 9px; }} .sk-line.tall {{ height: 26px; }}
.w30 {{ width: 30%; }} .w40 {{ width: 40%; }} .w45 {{ width: 45%; }} .w60 {{ width: 60%; }} .w70 {{ width: 70%; }} .w90 {{ width: 90%; }}
.sk.mt {{ margin-top: 10px; }}
.sk-card {{ border-radius: 14px; }} .sk-card.h56 {{ height: 56px; }}
.sk-input {{ height: 44px; border-radius: 12px; }}
.sk-btn {{ height: 44px; border-radius: 12px; background: linear-gradient(135deg, #0ea5e955, #6366f155); }}
.sk-pill {{ width: 96px; height: 24px; border-radius: 999px; }}
.sk-tab {{ height: 42px; border-radius: 12px; }}
.sk-sun {{ width: 110px; height: 110px; border-radius: 50%; }}
.sk-temp {{ width: 180px; height: 80px; border-radius: 16px; }}
.sk-panel {{ width: 38%; border-radius: 18px; }}
.sk-tile {{ height: 140px; border-radius: 16px; }}
.sk-hour {{ flex: 0 0 96px; height: 150px; border-radius: 16px; }}
.nc-loader {{ position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); width: min(360px, 86vw);
  background: var(--surface); border: 1px solid var(--border); border-radius: 20px; padding: 22px 24px 20px; text-align: center;
  box-shadow: 0 20px 60px rgba(2,6,23,{".18" if light else ".55"}); }}
.nc-loader-logo {{ width: 62px; height: 62px; margin: 0 auto 10px; border-radius: 18px; display: flex; align-items: center;
  justify-content: center; background: linear-gradient(135deg, #0ea5e9, #6366f1); box-shadow: 0 8px 22px rgba(99,102,241,.35);
  animation: nc-pulse 1.8s ease-in-out infinite; }}
@keyframes nc-pulse {{ 50% {{ transform: scale(1.06); }} }}
.nc-loader-t {{ font-weight: 800; font-size: 1.15rem; color: var(--ink); }}
.nc-loader-s {{ font-size: .76rem; color: var(--muted); margin-bottom: 12px; }}
.nc-loader-steps {{ position: relative; height: 20px; font-size: .84rem; color: var(--ink-2); }}
.nc-loader-steps span {{ position: absolute; inset: 0; opacity: 0; animation: nc-step 4.8s ease-in-out infinite; }}
@keyframes nc-step {{ 0% {{ opacity: 0; transform: translateY(4px); }} 8%, 30% {{ opacity: 1; transform: none; }}
  38%, 100% {{ opacity: 0; transform: translateY(-4px); }} }}
.nc-loader-bar {{ height: 5px; border-radius: 999px; background: var(--surface-2); overflow: hidden; margin-top: 14px; }}
.nc-loader-bar i {{ display: block; height: 100%; width: 40%; border-radius: 999px;
  background: linear-gradient(90deg, #0ea5e9, #6366f1); animation: nc-bar 1.3s ease-in-out infinite; }}
@keyframes nc-bar {{ 0% {{ transform: translateX(-110%); }} 100% {{ transform: translateX(260%); }} }}
@media (max-width: 900px) {{
  .nc-sk-side {{ display: none; }}
  .nc-sk-main {{ padding: 16px 12px; }}
  .nc-sk-search {{ grid-template-columns: 1fr 1fr; }}
  .nc-sk-tabs {{ grid-template-columns: repeat(3, 1fr); }}
  .nc-sk-tiles {{ grid-template-columns: repeat(2, 1fr); }}
  .nc-sk-hero {{ flex-direction: column; }} .sk-panel {{ width: 100%; height: 160px; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .sk, .nc-loader-logo, .nc-loader-bar i {{ animation: none !important; }}
  .nc-loader-steps span {{ animation: none; }} .nc-loader-steps span:last-child {{ opacity: 1; }}
}}

"""
