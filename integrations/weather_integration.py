"""Weather integration — current conditions and forecasts via Open-Meteo."""
from integrations.base import BaseIntegration
from integrations.weather_client import get_current_weather, get_weather_forecast
from utils.logger import get_logger

log = get_logger(__name__)


class WeatherIntegration(BaseIntegration):
    name = "weather"

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the current weather for any city or location.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City name or location, e.g. 'Mumbai', 'New Delhi', 'London'.",
                            }
                        },
                        "required": ["location"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weather_forecast",
                    "description": "Get a multi-day weather forecast (up to 7 days) for any city or location.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City name or location.",
                            },
                            "days": {
                                "type": "integer",
                                "description": "Number of forecast days (1–7). Defaults to 3.",
                                "default": 3,
                            },
                        },
                        "required": ["location"],
                    },
                },
            },
        ]

    def dispatch(self, tool_name: str, args: dict):
        if tool_name == "get_weather":
            try:
                data = get_current_weather(args["location"])
                return (
                    f"{data['location']}: {data['condition']}, "
                    f"{data['temperature_c']}°C (feels like {data['feels_like_c']}°C), "
                    f"humidity {data['humidity_pct']}%, wind {data['wind_kph']} km/h."
                )
            except Exception as e:
                log.warning("weather: get_weather failed", error=str(e))
                return f"Could not fetch weather: {e}"

        if tool_name == "get_weather_forecast":
            try:
                days = int(args.get("days", 3))
                data = get_weather_forecast(args["location"], days)
                lines = [f"Forecast for {data['location']}:"]
                for d in data["forecast"]:
                    lines.append(
                        f"  {d['date']}: {d['condition']}, "
                        f"{d['min_c']}–{d['max_c']}°C, "
                        f"rain {d['precipitation_mm']} mm"
                    )
                return "\n".join(lines)
            except Exception as e:
                log.warning("weather: get_weather_forecast failed", error=str(e))
                return f"Could not fetch forecast: {e}"

        return {"error": f"Unknown weather tool: {tool_name}"}
