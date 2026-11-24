import base64
import xml.etree.ElementTree as ET

import pytest

from weather_agent import analysis
from weather_agent.ui import charts, components, icons, theme
from weather_agent.weather_api import Location


@pytest.mark.parametrize("code,day,key", [
    (0, True, "clear-day"), (0, False, "clear-night"), (2, True, "partly-day"), (3, True, "overcast"),
    (45, True, "fog"), (53, True, "drizzle"), (63, True, "rain"), (82, True, "heavy-rain"),
    (73, True, "snow"), (95, True, "thunder"), (99, False, "thunder"), (None, True, "unknown"),
])
def test_code_to_icon_key(code, day, key):
    assert icons.code_to_key(code, day) == key


def _decode(img: str) -> str:
    b64 = img.split("base64,", 1)[1].split('"', 1)[0]
    return base64.b64decode(b64).decode("utf-8")


def test_every_wmo_code_renders_valid_svg_image():
    for code in [*analysis.WMO_CODES, None, 1234]:
        img = icons.weather_icon(code, True, 48)
        assert img.startswith('<img class="wx-icon" src="data:image/svg+xml;base64,')
        doc = _decode(img)
        ET.fromstring(doc)  # well-formed XML
        assert "@keyframes" in doc  # animation CSS travels inside the image


def test_animated_parts_present():
    assert "wx-spin" in icons.weather_svg_body(0, True)    # rotating sun rays
    assert "wx-fall" in icons.weather_svg_body(63, True)   # falling rain
    assert "wx-flash" in icons.weather_svg_body(95, True)  # lightning
    assert "wx-blow" in _decode(icons.wind_glyph())        # wind


def test_gauge_and_compass_are_images():
    for img in (components.risk_gauge(55, "High"), components.compass(225), components.small_arrow(90)):
        assert img.startswith("<img") and "<svg" not in img
        ET.fromstring(_decode(img))


def test_hero_and_tiles_render(snapshot):
    html = components.hero(snapshot) + components.tiles(snapshot) + components.hourly_strip(snapshot.hourly)
    assert "Lahore" in html and "Severe" in html and "wt-hour" in html


def test_city_names_are_escaped(snapshot):
    snapshot.location = Location("<script>alert(1)</script>", 1, 2, "X")
    html = components.hero(snapshot)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_aqi_badge_in_tile_uses_short_label_with_full_hover_text(snapshot):
    snapshot.air["category"] = "Unhealthy for sensitive groups"
    html = components.tiles(snapshot)
    assert ">Sensitive groups</span>" in html
    assert 'title="Unhealthy for sensitive groups"' in html


def test_status_pill_has_label_not_colour_only():
    pill = components.status_pill("High")
    assert "High" in pill and "▲" in pill


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_charts_build_in_both_themes(snapshot, mode):
    pal = theme.palette(mode)
    df = charts.hourly_frame(snapshot.hourly)
    for chart in (charts.temperature(df, pal), charts.humidity(df, pal), charts.rain_chance(df, pal),
                  charts.precipitation(df, pal), charts.wind(df, pal), charts.storm(df, pal),
                  charts.aqi(snapshot.air_hourly, pal)):
        assert chart.to_dict()["layer"]


@pytest.mark.parametrize("metric", list(charts.HEATMAP_METRICS))
def test_pakistan_heatmap_and_rankings(metric):
    from tests.test_app import PK_MATRIX, PK_ROW

    pal = theme.palette("light")
    assert charts.heatmap(PK_MATRIX, metric, pal, ["Lahore"]).to_dict()
    assert charts.ranking([PK_ROW], pal).to_dict()
    assert charts.rain_ranking([PK_ROW], pal).to_dict()


def test_daily_cards_render():
    days = [{"date": f"2026-07-{15 + i}", "weather_code": c, "temperature_2m_min": 20 + i, "temperature_2m_max": 30 + i,
             "precipitation_sum": 1.5, "precipitation_probability_max": 60, "wind_speed_10m_max": 20,
             "wind_gusts_10m_max": 40, "wind_direction_10m_dominant": 200, "sunrise": "2026-07-15T05:10",
             "sunset": "2026-07-15T19:10", "uv_index_max": 9.1} for i, c in enumerate([0, 3, 63, 95, 2, 1, 0])]
    html = components.daily_cards(days)
    assert html.count('class="wt-day"') == 7 and "Today" in html and "05:10" in html


def test_css_differs_per_theme_and_has_no_tag_text():
    import re

    for mode in ("dark", "light"):
        css = theme.build_css(mode)
        inner = css.strip()[len("<style>"):-len("</style>")]
        assert not re.search(r"<[/A-Za-z!]", inner)
    assert theme.build_css("dark") != theme.build_css("light")
    assert 'stExpandSidebarButton' in theme.build_css("dark")  # re-open control stays styled & visible


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_skeleton_overlay_css_hides_when_ready_with_failsafe(mode):
    from weather_agent.ui import skeleton

    css = theme.build_css(mode)
    assert "body:has(.nc-ready) .nc-boot" in css  # fades out when the last element arrives
    assert "nc-failsafe" in css and "40s" in css  # never blocks the page if the script stops early
    html = skeleton.overlay("NeuralCast", "Neural ThinkPad", "<Lahore>")
    assert "nc-loader" in html and "&lt;Lahore&gt;" in html and "<Lahore>" not in html


def test_html_table_escapes_but_allows_trusted_html_columns():
    html = components.table([{"a": "<b>x</b>", "b_html": components.status_pill("Low")}], [("a", "A"), ("b_html", "B")])
    assert "&lt;b&gt;x&lt;/b&gt;" in html and 'class="wt-status' in html
