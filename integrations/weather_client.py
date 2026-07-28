"""
Weather client using Open-Meteo (free, no API key required).
Geocoding via the Open-Meteo geocoding API.
"""
import httpx
from utils.logger import get_logger

log = get_logger(__name__)

WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


def _geocode(location: str) -> tuple[float, float, str]:
    """Return (lat, lon, resolved_name) for a location string."""
    r = httpx.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1, "language": "en", "format": "json"},
        timeout=8,
    )
    r.raise_for_status()
    results = r.json().get("results")
    if not results:
        raise ValueError(f"Location '{location}' not found.")
    hit = results[0]
    name = f"{hit['name']}, {hit.get('country', '')}".strip(", ")
    return hit["latitude"], hit["longitude"], name


def get_current_weather(location: str) -> dict:
    """Return current weather for a location."""
    lat, lon, resolved = _geocode(location)
    r = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,apparent_temperature,weathercode,windspeed_10m,relative_humidity_2m",
            "timezone": "auto",
            "forecast_days": 1,
        },
        timeout=8,
    )
    r.raise_for_status()
    data = r.json()
    cur = data["current"]
    code = cur.get("weathercode", 0)
    return {
        "location": resolved,
        "condition": WMO_CODES.get(code, "Unknown"),
        "temperature_c": cur.get("temperature_2m"),
        "feels_like_c": cur.get("apparent_temperature"),
        "humidity_pct": cur.get("relative_humidity_2m"),
        "wind_kph": cur.get("windspeed_10m"),
    }


def get_weather_forecast(location: str, days: int = 3) -> dict:
    """Return a multi-day weather forecast for a location."""
    days = max(1, min(days, 7))
    lat, lon, resolved = _geocode(location)
    r = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat, "longitude": lon,
            "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
            "forecast_days": days,
        },
        timeout=8,
    )
    r.raise_for_status()
    data = r.json()
    daily = data["daily"]
    forecast = []
    for i in range(len(daily["time"])):
        code = daily["weathercode"][i]
        forecast.append({
            "date": daily["time"][i],
            "condition": WMO_CODES.get(code, "Unknown"),
            "max_c": daily["temperature_2m_max"][i],
            "min_c": daily["temperature_2m_min"][i],
            "precipitation_mm": daily["precipitation_sum"][i],
        })
    return {"location": resolved, "forecast": forecast}
