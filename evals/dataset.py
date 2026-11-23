"""Evaluation dataset for the weather & storm agent.

Weather changes every hour, so references describe expected BEHAVIOUR (which tools are used,
which facts must be covered), not fixed numbers.
"""

DATASET_NAME = "weather-storm-agent-eval"

EXAMPLES: list[dict] = [
    {
        "inputs": {"question": "Will it rain or storm in Lahore in the next 6 hours?"},
        "outputs": {"city": "Lahore", "expected_tools": ["get_rain_storm_forecast"],
                    "must_cover": ["rain probability", "storm risk level", "timing"]},
    },
    {
        "inputs": {"question": "What is the live air speed, air direction, humidity and AQI in Karachi?"},
        "outputs": {"city": "Karachi", "expected_tools": ["get_live_weather"],
                    "must_cover": ["wind speed", "wind direction", "humidity", "air quality index"]},
    },
    {
        "inputs": {"question": "Scan Pakistani cities for rain and thunderstorms in the next 12 hours."},
        "outputs": {"city": "Pakistan", "expected_tools": ["pakistan_rain_storm_scan"],
                    "must_cover": ["multiple Pakistani cities", "storm risk ranking"]},
    },
    {
        "inputs": {"question": "How is the air quality in Peshawar and is it safe to go jogging?"},
        "outputs": {"city": "Peshawar", "expected_tools": ["get_air_quality"],
                    "must_cover": ["US AQI value", "AQI category", "health advice"]},
    },
    {
        "inputs": {"question": "Current weather in Tokyo and any storms expected in the next 24 hours?"},
        "outputs": {"city": "Tokyo", "expected_tools": ["get_live_weather", "get_rain_storm_forecast"],
                    "must_cover": ["current conditions", "storm outlook"]},
    },
    {
        "inputs": {"question": "Create a news-ready PDF report named 'Islamabad Storm Watch' on the next 12 hours."},
        "outputs": {"city": "Islamabad", "expected_tools": ["save_analysis_report"],
                    "must_cover": ["pdf file name", "storm outlook"]},
    },
    {
        "inputs": {"question": "What's the weather in Atlantis-on-Mars?"},
        "outputs": {"city": "Atlantis-on-Mars", "expected_tools": ["get_live_weather"],
                    "must_cover": ["says the city could not be found", "no invented numbers"]},
    },
]
