import json
import os
import requests
from dotenv import load_dotenv
import core.timeutils as core_time

load_dotenv()

class WeatherInjector:
    """
    Generates fresh context injection (time and environment) on every call.
    No caching, no state files.
    """

    def __init__(self):
        self.lat = os.getenv("LAT")
        self.lon = os.getenv("LON")
        self.tz = os.getenv("TZ")
        self.units = os.getenv("UNITS") or "metric"
        self.api_key = os.getenv("OPENWEATHER_API_KEY")

    def fetch_sunrise_sunset(self):
        url = "https://api.sunrise-sunset.org/json"
        params = {"lat": self.lat, "lng": self.lon, "formatted": 0}
        if self.tz:
            params["tzid"] = self.tz
        try:
            r = requests.get(url, params=params, timeout=5) # Short timeout to not block chat
            r.raise_for_status()
            data = r.json() or {}
            return data.get("results", {}) or {}
        except Exception:
            return {}

    def fetch_weather_openweather(self):
        if not self.api_key:
            return None
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"lat": self.lat, "lon": self.lon, "appid": self.api_key, "units": self.units}
        try:
            r = requests.get(url, params=params, timeout=5) # Short timeout
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def build_injection_text(self) -> str:
        # Always fetch fresh data
        ss = self.fetch_sunrise_sunset()
        sunrise = ss.get("sunrise", "")
        sunset = ss.get("sunset", "")

        # Trim ISO timestamps → HH:MM if present
        if "T" in sunrise:
            sunrise = sunrise.split("T")[1][:5]
        if "T" in sunset:
            sunset = sunset.split("T")[1][:5]

        weather_line = ""
        w = self.fetch_weather_openweather()
        if w:
            temp = w.get("main", {}).get("temp")
            condition = ((w.get("weather") or [{}])[0].get("main") or "").lower()
            unit = "°C" if self.units == "metric" else ("°F" if self.units == "imperial" else "K")
            if temp is not None and condition:
                weather_line = f"• Weather: {round(temp)}{unit}, {condition}"
            elif temp is not None:
                weather_line = f"• Weather: {round(temp)}{unit}"
            elif condition:
                weather_line = f"• Weather: {condition}"
        
        dt = core_time.local_dt()

        header = "Context update (time and environment)"
        lines = [
            header,
            "",
            f"• {dt.strftime('%A, %B %d, %Y')} ({core_time.weekday_label()})",
            f"• Local time: {dt.strftime('%H:%M')} — {core_time.time_of_day_label(dt.hour)}",
            f"• Sunrise: {sunrise}",
            f"• Sunset: {sunset}",
        ]
        if weather_line:
            lines.append(weather_line)
            
        return "\n".join(lines)

    def weather_updater(self):
        return self.build_injection_text()
