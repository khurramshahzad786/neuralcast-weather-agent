"""Animated SVG weather icons (sun, moon, clouds, rain, storm, snow, fog, wind).

Streamlit's ``st.html`` sanitizer strips inline ``<svg>``, so every icon is emitted as a
self-contained SVG document inside ``<img src="data:image/svg+xml;base64,...">``. The
animation CSS travels inside each SVG (``ICON_CSS``) and is disabled for users who prefer
reduced motion.
"""

from __future__ import annotations

import base64
from html import escape

ICON_CSS = """
.wx-spin{transform-box:fill-box;transform-origin:center;animation:wx-spin 22s linear infinite}
.wx-drift{animation:wx-drift 5s ease-in-out infinite alternate}
.wx-fall{animation:wx-fall 1.1s linear infinite}
.wx-snow{animation:wx-snow 2.6s linear infinite}
.wx-flash{animation:wx-flash 3.2s ease-in-out infinite}
.wx-blow{animation:wx-blow 2.6s ease-in-out infinite}
@keyframes wx-spin{to{transform:rotate(360deg)}}
@keyframes wx-drift{from{transform:translateX(-1.5px)}to{transform:translateX(2px)}}
@keyframes wx-fall{0%{transform:translateY(-4px);opacity:0}30%{opacity:1}100%{transform:translateY(7px);opacity:0}}
@keyframes wx-snow{0%{transform:translateY(-4px);opacity:0}30%{opacity:1}100%{transform:translateY(6px);opacity:0}}
@keyframes wx-flash{0%,70%,100%{opacity:1}74%{opacity:.15}78%{opacity:1}82%{opacity:.3}}
@keyframes wx-blow{0%,100%{transform:translateX(-2px);opacity:.65}50%{transform:translateX(2.5px);opacity:1}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


# Soft shadow so light clouds stay visible on white cards (light theme) and pop on dark ones.
SHADOW_DEFS = ('<defs><filter id="sh" x="-20%" y="-20%" width="140%" height="150%">'
               '<feDropShadow dx="0" dy="1.2" stdDeviation="1.3" flood-color="#0f172a" flood-opacity="0.35"/>'
               "</filter></defs>")


def to_img(svg_body: str, width: int, height: int, label: str, view_box: str = "0 0 64 64",
           css_class: str = "wx-icon") -> str:
    """Wrap SVG markup in a standalone document and return an ``<img>`` data-URI tag."""
    doc = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{view_box}">'
           f"<style>{ICON_CSS}</style>{SHADOW_DEFS}{svg_body}</svg>")
    b64 = base64.b64encode(doc.encode("utf-8")).decode("ascii")
    return (f'<img class="{css_class}" src="data:image/svg+xml;base64,{b64}" width="{width}" '
            f'height="{height}" alt="{escape(label)}" title="{escape(label)}"/>')

SUN = "#fbbf24"
SUN_CORE = "#fcd34d"
MOON = "#e2e8f0"
CLOUD_FRONT = "#e5edf7"
CLOUD_BACK = "#94a3b8"
CLOUD_DARK = "#64748b"
CLOUD_STORM = "#475569"
RAIN = "#60a5fa"
BOLT = "#facc15"
SNOW = "#e0f2fe"
WIND = "#38bdf8"


def _svg(body: str, size: int, label: str) -> str:
    return to_img(body, size, size, label)


def _sun(cx: float = 32, cy: float = 32, r: float = 10, rays: bool = True) -> str:
    out = ""
    if rays:
        lines = []
        for i in range(8):
            angle = i * 45
            lines.append(
                f'<line x1="{cx}" y1="{cy - r - 4}" x2="{cx}" y2="{cy - r - 10}" '
                f'transform="rotate({angle} {cx} {cy})" />'
            )
        out += (f'<g class="wx-spin" stroke="{SUN}" stroke-width="3.2" stroke-linecap="round">'
                + "".join(lines) + "</g>")
    out += f'<circle cx="{cx}" cy="{cy}" r="{r + 3}" fill="{SUN}" opacity="0.25"/>'
    out += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{SUN_CORE}"/>'
    return out


def _moon(cx: float = 32, cy: float = 30, r: float = 13) -> str:
    crescent = (f"M{cx} {cy - r} A{r} {r} 0 0 0 {cx} {cy + r} "
                f"A{r * 0.55:.1f} {r} 0 0 1 {cx} {cy - r} Z")
    return (f'<circle cx="{cx - r * 0.3:.1f}" cy="{cy}" r="{r + 3}" fill="{MOON}" opacity=".12"/>'
            f'<path d="{crescent}" fill="{MOON}" stroke="#94a3b8" stroke-width=".6" filter="url(#sh)" '
            f'transform="rotate(-25 {cx} {cy})"/>'
            f'<circle cx="{cx + r * 0.9:.1f}" cy="{cy - r * 0.8:.1f}" r="1.4" fill="{MOON}" opacity=".8"/>'
            f'<circle cx="{cx + r * 1.2:.1f}" cy="{cy + r * 0.2:.1f}" r="1" fill="{MOON}" opacity=".55"/>')


def _cloud(fill: str, dx: float = 0, dy: float = 0, scale: float = 1.0, drift: bool = True) -> str:
    cls = ' class="wx-drift"' if drift else ""
    return (f'<g{cls} transform="translate({dx} {dy}) scale({scale})" fill="{fill}" filter="url(#sh)">'
            '<circle cx="21" cy="38" r="8"/><circle cx="31" cy="31" r="11"/>'
            '<circle cx="43" cy="37" r="9"/><rect x="13" y="37" width="38" height="9" rx="4.5"/>'
            "</g>")


def _drops(n: int, color: str = RAIN, heavy: bool = False) -> str:
    xs = [20, 28, 36, 44][:n] if n <= 4 else [18, 24, 30, 36, 42, 48][:n]
    length = 7 if heavy else 5
    out = []
    for i, x in enumerate(xs):
        out.append(f'<line class="wx-fall" style="animation-delay:{i * 0.27:.2f}s" x1="{x}" y1="50" '
                   f'x2="{x - 2}" y2="{50 + length}" stroke="{color}" stroke-width="{2.6 if heavy else 2.2}" '
                   'stroke-linecap="round"/>')
    return "".join(out)


def _flakes() -> str:
    out = []
    for i, x in enumerate((21, 32, 43)):
        out.append(f'<g class="wx-snow" style="animation-delay:{i * 0.5:.1f}s" stroke="{SNOW}" '
                   f'stroke-width="1.8" stroke-linecap="round">'
                   f'<line x1="{x}" y1="49" x2="{x}" y2="57"/><line x1="{x - 4}" y1="53" x2="{x + 4}" y2="53"/>'
                   f'<line x1="{x - 3}" y1="50" x2="{x + 3}" y2="56"/><line x1="{x + 3}" y1="50" x2="{x - 3}" y2="56"/>'
                   "</g>")
    return "".join(out)


def _bolt() -> str:
    return (f'<path class="wx-flash" d="M33 42 L26 53 H32 L29 62 L40 49 H34 L38 42 Z" fill="{BOLT}" '
            'stroke="#a16207" stroke-width=".6"/>')


def _fog_lines() -> str:
    return "".join(
        f'<line class="wx-blow" style="animation-delay:{i * 0.4:.1f}s" x1="{14 + i * 3}" y1="{50 + i * 5}" '
        f'x2="{50 - i * 2}" y2="{50 + i * 5}" stroke="{CLOUD_BACK}" stroke-width="2.6" stroke-linecap="round"/>'
        for i in range(3)
    )


def wind_glyph(size: int = 28, color: str = WIND) -> str:
    body = (f'<g fill="none" stroke="{color}" stroke-width="3.2" stroke-linecap="round">'
            '<path class="wx-blow" d="M8 24 H40 a7 7 0 1 0 -7 -7"/>'
            '<path class="wx-blow" style="animation-delay:.3s" d="M8 34 H50 a7 7 0 1 1 -7 7"/>'
            '<path class="wx-blow" style="animation-delay:.6s" d="M8 44 H30"/></g>')
    return _svg(body, size, "wind")


def droplet(size: int = 28) -> str:
    body = (f'<path d="M32 8 C32 8 16 28 16 39 a16 16 0 0 0 32 0 C48 28 32 8 32 8z" fill="{RAIN}" opacity=".9"/>'
            '<path d="M24 40 a8 8 0 0 0 8 8" stroke="#dbeafe" stroke-width="3" fill="none" stroke-linecap="round"/>')
    return _svg(body, size, "humidity")


def gauge_glyph(size: int = 28) -> str:
    body = ('<path d="M10 42 a22 22 0 0 1 44 0" fill="none" stroke="#a78bfa" stroke-width="5" stroke-linecap="round"/>'
            '<line x1="32" y1="42" x2="44" y2="26" stroke="#e5edf7" stroke-width="3.5" stroke-linecap="round"/>'
            '<circle cx="32" cy="42" r="4" fill="#e5edf7"/>')
    return _svg(body, size, "pressure")


def leaf(size: int = 28) -> str:
    body = ('<path d="M14 50 C14 24 30 12 52 12 C52 34 40 50 14 50z" fill="#34d399" opacity=".9"/>'
            '<path d="M14 50 L40 24" stroke="#064e3b" stroke-width="2.4" stroke-linecap="round"/>')
    return _svg(body, size, "air quality")


def cloud_glyph(size: int = 28) -> str:
    return _svg(_cloud(CLOUD_FRONT, 0, -4, drift=False), size, "cloud cover")


def dust_glyph(size: int = 28) -> str:
    body = "".join(f'<circle class="wx-drift" cx="{x}" cy="{y}" r="{r}" fill="#d6a76a" opacity="{o}"/>'
                   for x, y, r, o in ((16, 22, 3, .9), (30, 18, 2.4, .7), (44, 26, 3.4, .85), (22, 36, 2.2, .6),
                                      (36, 34, 3, .8), (50, 40, 2.2, .6), (14, 46, 2.6, .7), (30, 48, 3.2, .85)))
    return _svg(body, size, "dust")


def storm_glyph(size: int = 28) -> str:
    return _svg(_cloud(CLOUD_STORM, 0, -6, drift=False) + _bolt(), size, "storm")


def thermometer(size: int = 28) -> str:
    body = ('<rect x="26" y="8" width="12" height="36" rx="6" fill="none" stroke="#e5edf7" stroke-width="3"/>'
            '<circle cx="32" cy="48" r="9" fill="#f97316"/><rect x="29.5" y="22" width="5" height="26" rx="2.5" fill="#f97316"/>')
    return _svg(body, size, "temperature")


def code_to_key(code, is_day: bool = True) -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return "unknown"
    if c == 0:
        return "clear-day" if is_day else "clear-night"
    if c in (1, 2):
        return "partly-day" if is_day else "partly-night"
    if c == 3:
        return "overcast"
    if c in (45, 48):
        return "fog"
    if c in (51, 53, 55, 56, 57):
        return "drizzle"
    if c in (61, 63, 66, 80, 81):
        return "rain"
    if c in (65, 67, 82):
        return "heavy-rain"
    if c in (71, 73, 75, 77, 85, 86):
        return "snow"
    if c in (95, 96, 99):
        return "thunder"
    return "unknown"


def weather_icon(code, is_day: bool = True, size: int = 64) -> str:
    """Animated ``<img>`` icon for a WMO weather code."""
    return _svg(weather_svg_body(code, is_day), size, code_to_key(code, is_day).replace("-", " "))


def weather_svg_body(code, is_day: bool = True) -> str:
    """Raw SVG body (64x64 view box) for a WMO weather code."""
    key = code_to_key(code, is_day)
    if key == "clear-day":
        body = _sun(32, 32, 11)
    elif key == "clear-night":
        body = _moon()
    elif key == "partly-day":
        body = _sun(24, 22, 8) + _cloud(CLOUD_FRONT, 6, 4, 0.85)
    elif key == "partly-night":
        body = _moon(26, 22, 10) + _cloud(CLOUD_FRONT, 6, 4, 0.85)
    elif key == "overcast":
        body = _cloud(CLOUD_BACK, 8, -8, 0.8) + _cloud(CLOUD_FRONT, -2, 0)
    elif key == "fog":
        body = _cloud(CLOUD_BACK, 0, -8, drift=False) + _fog_lines()
    elif key == "drizzle":
        body = _cloud(CLOUD_FRONT, 0, -6) + _drops(3)
    elif key == "rain":
        body = _cloud(CLOUD_BACK, 0, -6) + _drops(4)
    elif key == "heavy-rain":
        body = _cloud(CLOUD_DARK, 0, -6) + _drops(6, heavy=True)
    elif key == "snow":
        body = _cloud(CLOUD_FRONT, 0, -6) + _flakes()
    elif key == "thunder":
        body = _cloud(CLOUD_STORM, 0, -8) + _drops(2) + _bolt()
    else:
        body = _cloud(CLOUD_BACK, 0, -4, drift=False)
    return body


# Hero background mood per icon key (subtle gradients over the dark surface).
MOODS = {
    "clear-day": ("#f59e0b", "#0ea5e9"),
    "clear-night": ("#4338ca", "#0f172a"),
    "partly-day": ("#f59e0b", "#64748b"),
    "partly-night": ("#4338ca", "#334155"),
    "overcast": ("#64748b", "#1e293b"),
    "fog": ("#94a3b8", "#1e293b"),
    "drizzle": ("#38bdf8", "#1e293b"),
    "rain": ("#2563eb", "#0f172a"),
    "heavy-rain": ("#1d4ed8", "#020617"),
    "snow": ("#bae6fd", "#1e293b"),
    "thunder": ("#7c3aed", "#020617"),
    "unknown": ("#334155", "#0f172a"),
}
