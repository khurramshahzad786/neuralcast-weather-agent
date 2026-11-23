import pytest

from weather_agent import analysis
from tests.conftest import make_rows


@pytest.mark.parametrize("deg,expected", [(0, "N"), (90, "E"), (180, "S"), (225, "SW"), (359, "N"), (None, "n/a")])
def test_wind_compass(deg, expected):
    assert analysis.wind_compass(deg) == expected


@pytest.mark.parametrize("aqi,cat", [(10, "Good"), (51, "Moderate"), (150, "Unhealthy for sensitive groups"),
                                     (151, "Unhealthy"), (250, "Very unhealthy"), (400, "Hazardous"),
                                     (None, "Unknown")])
def test_aqi_category(aqi, cat):
    assert analysis.aqi_category(aqi) == cat


def test_beaufort_scale():
    assert analysis.beaufort(0)[0] == 0
    assert analysis.beaufort(65) == (8, "Gale")
    assert analysis.beaufort(130)[0] == 12


def test_calm_hour_scores_low():
    row = make_rows(1, storm_at=None)[0]
    assert analysis.hour_storm_score(row) < 20
    assert analysis.risk_level(analysis.hour_storm_score(row)) == "Low"


def test_thunderstorm_hour_scores_severe():
    row = make_rows(4, storm_at=3)[3]
    score = analysis.hour_storm_score(row)
    assert score >= 70
    assert analysis.risk_level(score) == "Severe"


def test_analyse_hours_finds_storm_and_rain():
    rows = make_rows(6, storm_at=3)
    o = analysis.analyse_hours(rows)
    assert o["storm_risk"] == "Severe"
    assert o["peak_storm_time"] == rows[3]["time"]
    assert o["thunderstorm_hours"] == [rows[3]["time"]]
    assert o["rain_expected"] is True
    assert o["first_rain_time"] == rows[3]["time"]
    assert o["max_gust_kmh"] == 75.0
    assert o["peak_rain_intensity"] == "heavy"
    assert o["pressure_trend_hpa"] == -5.0


def test_analyse_hours_dry():
    o = analysis.analyse_hours(make_rows(6, storm_at=None))
    assert o["rain_expected"] is False and o["storm_risk"] == "Low" and o["first_rain_time"] is None


def test_analyse_hours_empty():
    assert analysis.analyse_hours([])["storm_risk"] == "Unknown"


def test_dust_storm_risk():
    assert analysis.dust_storm_risk(55, 70, 20, 300, 200) == "High"
    assert analysis.dust_storm_risk(40, 40, 30, 160, 0) == "Moderate"
    assert analysis.dust_storm_risk(10, 15, 80, 50, 5) == "Low"


def test_missing_values_do_not_crash():
    assert analysis.hour_storm_score({"time": "x"}) >= 0
    assert analysis.describe_code(None) == "Unknown"
