"""PDF report generation (ReportLab + Matplotlib).

Each analysis is saved as its own PDF named after the analysis, e.g.
``data/reports/lahore-storm-watch_20261123-1515.pdf``.
"""

from __future__ import annotations

import io
import json
import re
import secrets
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from . import config  # noqa: E402
from .analysis import describe_code, wind_compass  # noqa: E402
from .service import CitySnapshot  # noqa: E402

RISK_COLORS = {
    "Low": colors.HexColor("#2e7d32"),
    "Moderate": colors.HexColor("#f9a825"),
    "High": colors.HexColor("#ef6c00"),
    "Severe": colors.HexColor("#c62828"),
}


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (slug or "weather-analysis")[:max_len].rstrip("-")


def _latin1(text: Any) -> str:
    """ReportLab's built-in fonts are Latin-1; drop emoji and other symbols."""
    s = str(text if text is not None else "")
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"').replace("\u2022", "-").replace("\u2192", "->")
    return s.encode("latin-1", "ignore").decode("latin-1")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markdown_to_flowables(md: str, styles) -> list:
    """Minimal Markdown -> ReportLab (headings, bullets, bold, italics, paragraphs)."""
    flow: list = []
    para: list[str] = []

    def inline(s: str) -> str:
        s = _escape(_latin1(s))
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", s)
        s = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", s)
        return s

    def flush():
        if para:
            flow.append(Paragraph(inline(" ".join(para)), styles["BodyText"]))
            para.clear()

    for raw in md.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("|"):  # markdown tables -> monospace line
            flush()
            if not re.fullmatch(r"\|?[\s:\-|]+\|?", stripped):
                flow.append(Paragraph(inline(stripped), styles["Code"]))
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", stripped)
        if m:
            flush()
            level = len(m.group(1))
            style = styles["Heading2"] if level <= 2 else styles["Heading3"]
            flow.append(Paragraph(inline(m.group(2)), style))
            continue
        m = re.match(r"^([-*+]|\d+[.)])\s+(.*)", stripped)
        if m:
            flush()
            flow.append(Paragraph(inline(m.group(2)), styles["Bullet"], bulletText="-"))
            continue
        para.append(stripped)
    flush()
    return flow


def _chart(snapshot: CitySnapshot) -> io.BytesIO | None:
    rows = snapshot.hourly
    if not rows:
        return None
    labels = [r["time"][-5:] for r in rows]
    x = range(len(rows))
    temp = [r.get("temperature_2m") for r in rows]
    pop = [r.get("precipitation_probability") or 0 for r in rows]
    gust = [r.get("wind_gusts_10m") or 0 for r in rows]
    wind = [r.get("wind_speed_10m") or 0 for r in rows]

    # One measure per panel (no dual axes); validated palette: blue / orange / aqua.
    fig, (ax0, ax1, ax2) = plt.subplots(3, 1, figsize=(8, 5.6), sharex=True)
    for ax in (ax0, ax1, ax2):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#e1e0d9", linewidth=0.6)
        ax.tick_params(labelsize=7, colors="#52514e")
    ax0.plot(x, temp, color="#eb6834", linewidth=2)
    ax0.set_ylabel("Temp (C)", fontsize=8)
    ax0.set_title(f"Next {len(rows)} hours - {snapshot.location.label}", fontsize=10, loc="left")

    ax1.bar(x, pop, color="#2a78d6", width=0.7)
    ax1.set_ylim(0, 100)
    ax1.set_ylabel("Rain chance (%)", fontsize=8)

    ax2.plot(x, wind, color="#2a78d6", linewidth=2, label="Wind")
    ax2.plot(x, gust, color="#eb6834", linewidth=2, linestyle="--", label="Gusts")
    if max(gust or [0]) >= 40:
        ax2.axhline(62, color="#d03b3b", linewidth=0.8, linestyle=":", label="Gale (62)")
    ax2.set_ylabel("km/h", fontsize=8)
    ax2.legend(fontsize=7, loc="upper left", frameon=False, ncol=3)
    step = max(1, len(rows) // 12)
    ax2.set_xticks(list(x)[::step])
    ax2.set_xticklabels(labels[::step], rotation=45, fontsize=7)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf


_CELL = ParagraphStyle("Cell", fontName="Helvetica", fontSize=9, leading=11)


def _kv_table(pairs: list[tuple[str, Any]], col_widths=(6 * cm, 10.5 * cm)) -> Table:
    data = [[_latin1(k), Paragraph(_escape(_latin1(v if v is not None else "n/a")), _CELL)]
            for k, v in pairs]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eceff1")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b0bec5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _hourly_table(snapshot: CitySnapshot, max_rows: int = 24) -> Table:
    header = ["Time", "Weather", "Temp C", "RH %", "Rain %", "mm", "Wind", "Gust", "CAPE"]
    data = [header]
    for r in snapshot.hourly[:max_rows]:
        data.append([
            r["time"][5:].replace("T", " "),
            _latin1(describe_code(r.get("weather_code")))[:22],
            r.get("temperature_2m"),
            r.get("relative_humidity_2m"),
            r.get("precipitation_probability"),
            r.get("precipitation"),
            f"{r.get('wind_speed_10m')} {wind_compass(r.get('wind_direction_10m'))}",
            r.get("wind_gusts_10m"),
            r.get("cape"),
        ])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565c0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cfd8dc")),
    ]))
    return t


def build_pdf(
    snapshot: CitySnapshot,
    analysis_name: str,
    analysis_markdown: str,
    model_name: str = "",
    out_dir: Path | None = None,
    tz: tzinfo | None = None,
    owner: str = "",
) -> Path:
    """Render a news-ready PDF and return its path. ``tz`` = reader's time zone for timestamps.

    ``owner`` = visitor id of the browser session that created it; only that visitor (and the site
    owner) can list it. Reports without an owner are visible to the site owner only."""
    out_dir = out_dir or config.REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    local = now.astimezone(tz) if tz else now
    zone = local.strftime("%Z") or "UTC"
    if zone.startswith(("+", "-")):
        zone = f"UTC{zone}"
    # random suffix: all visitors share this folder, so two reports with the same title in the same second
    # must never get the same file (that would hand one visitor's report to the other)
    path = out_dir / f"{slugify(analysis_name)}_{now:%Y%m%d-%H%M%S}-{secrets.token_hex(4)}.pdf"

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("TitleCenter", parent=styles["Title"], alignment=TA_CENTER, fontSize=18))
    styles.add(ParagraphStyle("Small", parent=styles["BodyText"], fontSize=8, textColor=colors.grey))
    styles["Code"].fontSize = 7.5

    o, c, a = snapshot.outlook, snapshot.current, snapshot.air
    risk = o.get("storm_risk", "Unknown")
    story: list = [
        Paragraph(_escape(_latin1(analysis_name)), styles["TitleCenter"]),
        Paragraph(
            _escape(_latin1(f"{snapshot.location.label}  |  {snapshot.location.latitude:.3f}, "
                            f"{snapshot.location.longitude:.3f}  |  Generated {local:%Y-%m-%d %H:%M} {zone}")),
            styles["Small"],
        ),
        Spacer(1, 8),
    ]

    badge = Table([[f"STORM RISK: {risk.upper()}   (score {o.get('max_storm_score', 0)}/100)"]],
                  colWidths=[16.5 * cm])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), RISK_COLORS.get(risk, colors.grey)),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [badge, Spacer(1, 10)]

    is_ai = model_name != "rule-based"
    story.append(Paragraph("AI analysis" if is_ai else "Analysis", styles["Heading2"]))
    story += markdown_to_flowables(analysis_markdown or "_No analysis text supplied._", styles)

    story.append(Paragraph("Live conditions", styles["Heading2"]))
    story.append(_kv_table([
        ("Observed at (local)", c.get("time")),
        ("Condition", c.get("condition")),
        ("Temperature / feels like", f"{c.get('temperature_c')} C / {c.get('feels_like_c')} C"),
        ("Air humidity", f"{c.get('humidity_pct')} %"),
        ("Air (wind) speed", f"{c.get('wind_speed_kmh')} km/h, gusts {c.get('wind_gusts_kmh')} km/h"),
        ("Air (wind) direction", f"{c.get('wind_direction')} ({c.get('wind_direction_deg')} deg)"),
        ("Beaufort scale", c.get("beaufort")),
        ("Pressure", f"{c.get('pressure_hpa')} hPa"),
        ("Cloud cover", f"{c.get('cloud_cover_pct')} %"),
    ]))

    story.append(Paragraph("Air quality", styles["Heading2"]))
    story.append(_kv_table([
        ("US AQI", f"{a.get('us_aqi')} - {a.get('category')}"),
        ("European AQI", a.get("european_aqi")),
        ("PM2.5 / PM10", f"{a.get('pm2_5')} / {a.get('pm10')} ug/m3"),
        ("Dust", f"{a.get('dust')} ug/m3"),
        ("Health advice", a.get("advice")),
        ("Dust-storm risk", snapshot.dust_storm_risk),
    ]))

    story.append(Paragraph(f"Rain and storm outlook (next {o.get('hours', 0)} h)", styles["Heading2"]))
    story.append(_kv_table([
        ("Rain expected", "Yes" if o.get("rain_expected") else "No"),
        ("First rain hour", o.get("first_rain_time") or "-"),
        ("Max rain probability", f"{o.get('max_precip_probability_pct')} % at {o.get('max_precip_probability_time')}"),
        ("Total precipitation", f"{o.get('total_precip_mm')} mm (peak intensity: {o.get('peak_rain_intensity')})"),
        ("Thunderstorm hours", ", ".join(h[-5:] for h in o.get("thunderstorm_hours", [])) or "None forecast"),
        ("Max gust", f"{o.get('max_gust_kmh')} km/h at {o.get('max_gust_time')}"),
        ("Max CAPE / min lifted index", f"{o.get('max_cape_jkg')} J/kg / {o.get('min_lifted_index')}"),
        ("Pressure trend", f"{o.get('pressure_trend_hpa')} hPa"),
    ]))

    chart = _chart(snapshot)
    if chart:
        story += [Spacer(1, 8), Image(chart, width=17 * cm, height=11.9 * cm)]

    story.append(Paragraph("Hourly forecast", styles["Heading2"]))
    story.append(_hourly_table(snapshot))
    story += [
        Spacer(1, 10),
        Paragraph(
            _escape(_latin1(
                "Weather data by Open-Meteo.com (CC BY 4.0). "
                + ((f"Analysis generated by an AI agent ({model_name}). " if model_name else
                    "Analysis generated by an AI agent. ") if is_ai else "Rule-based analysis. ")
                + "Forecasts are probabilistic; follow official PMD / NDMA advisories for warnings."
            )),
            styles["Small"],
        ),
    ]

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            title=_latin1(analysis_name), author="Weather Storm Agent")
    doc.build(story)
    _record(out_dir, {
        "file": path.name,
        "analysis_name": analysis_name,
        "city": snapshot.location.name,
        "country": snapshot.location.country,
        "storm_risk": risk,
        "storm_score": o.get("max_storm_score", 0),
        "rain_expected": bool(o.get("rain_expected")),
        "max_rain_prob_pct": o.get("max_precip_probability_pct"),
        "us_aqi": a.get("us_aqi"),
        "aqi_category": a.get("category"),
        "temperature_c": c.get("temperature_c"),
        "model": model_name or "",
        "created_at": now.isoformat(timespec="seconds"),
        "summary": (analysis_markdown or "")[:1500],
        "owner": owner,
    })
    return path


INDEX_FILE = "index.jsonl"


def _record(out_dir: Path, meta: dict[str, Any]) -> None:
    """Append report metadata to a JSON-lines index (searchable without an LLM key)."""
    with (out_dir / INDEX_FILE).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(meta, ensure_ascii=False, default=str) + "\n")


def list_reports(out_dir: Path | None = None) -> list[Path]:
    out_dir = out_dir or config.REPORTS_DIR
    if not out_dir.exists():
        return []
    return sorted(out_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)


def load_index(out_dir: Path | None = None) -> list[dict[str, Any]]:
    """Metadata for every PDF on disk, newest first (files without an index entry get basic info)."""
    out_dir = out_dir or config.REPORTS_DIR
    entries: dict[str, dict[str, Any]] = {}
    idx = out_dir / INDEX_FILE
    if idx.exists():
        for line in idx.read_text(encoding="utf-8").splitlines():
            try:
                meta = json.loads(line)
            except ValueError:
                continue
            if isinstance(meta, dict) and meta.get("file"):
                entries[meta["file"]] = meta
    out = []
    for p in list_reports(out_dir):
        stat = p.stat()
        meta = dict(entries.get(p.name) or {
            "file": p.name, "analysis_name": p.stem.split("_", 1)[0].replace("-", " ").title(),
            "city": "", "storm_risk": "Unknown", "summary": "",
            "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
        })
        meta["size_kb"] = round(stat.st_size / 1024, 1)
        meta["path"] = p
        out.append(meta)
    return out


def visible_index(owner: str, see_all: bool = False, out_dir: Path | None = None) -> list[dict[str, Any]]:
    """Reports a viewer may see: the ones their own session created, or all of them for the site owner.

    Deny by default: an empty ``owner`` sees nothing, and untagged (older) reports are owner-only.
    UI code must use this, not ``load_index``."""
    entries = load_index(out_dir)
    if see_all:
        return entries
    if not owner:
        return []
    return [e for e in entries if e.get("owner") == owner]


def search_reports(entries: list[dict[str, Any]], query: str = "", risks: list[str] | None = None,
                   city: str | None = None) -> list[dict[str, Any]]:
    """Keyword search + filters over the report index. Results ranked by term hits, then recency."""
    terms = [t for t in re.split(r"\W+", query.lower()) if t]
    results = []
    for e in entries:
        if risks and e.get("storm_risk") not in risks:
            continue
        if city and city.lower() not in str(e.get("city", "")).lower():
            continue
        hay = " ".join(str(e.get(k, "")) for k in ("analysis_name", "city", "country", "storm_risk",
                                                   "aqi_category", "summary")).lower()
        hits = sum(hay.count(t) for t in terms)
        if terms and not hits:
            continue
        results.append((hits, e.get("created_at", ""), e))
    results.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [e for _, _, e in results]
