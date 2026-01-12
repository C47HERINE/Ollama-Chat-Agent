from dotenv import load_dotenv
import core.timeutils as core_time
import os, json, requests

load_dotenv()

class WeatherInjector:
    """Hourly background context injection (based on local date + hour)."""
    def __init__(self, low_dir="./user/low", state_file="weather_state.json"):
        self.state_dir = low_dir
        self.state_path = os.path.join(low_dir, state_file)
        os.makedirs(self.state_dir, exist_ok=True)
        self.lat = os.getenv("LAT")
        self.lon = os.getenv("LON")
        self.tz = os.getenv("TZ")
        self.units = os.getenv("UNITS") or "metric"
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        self.state = self.load_state()

    def load_state(self):
        default = {"last_date": "", "last_hour": -1}
        if not os.path.exists(self.state_path):
            return default
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return default
            last_date = data.get("last_date", "")
            last_hour = data.get("last_hour", -1)
            if not isinstance(last_date, str):
                last_date = ""
            if not isinstance(last_hour, int):
                last_hour = -1
            return {"last_date": last_date, "last_hour": last_hour}
        except (OSError, ValueError, json.JSONDecodeError):
            return default

    def save_state(self):
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def should_update_now(self) -> bool:
        if not self.lat or not self.lon:
            return False
        dt = core_time.local_dt()
        now_date = dt.strftime("%Y-%m-%d")
        now_hour = dt.hour
        last_date = self.state.get("last_date", "")
        last_hour = self.state.get("last_hour", -1)
        return (last_date != now_date) or (last_hour != now_hour)

    def mark_updated(self):
        dt = core_time.local_dt()
        self.state["last_date"] = dt.strftime("%Y-%m-%d")
        self.state["last_hour"] = dt.hour
        self.save_state()

    def fetch_sunrise_sunset(self):
        url = "https://api.sunrise-sunset.org/json"
        params = {"lat": self.lat, "lng": self.lon, "formatted": 0}
        if self.tz:
            params["tzid"] = self.tz
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json() or {}
        return data.get("results", {}) or {}

    def fetch_weather_openweather(self):
        if not self.api_key:
            return None
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"lat": self.lat, "lon": self.lon, "appid": self.api_key, "units": self.units}
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def build_injection_text(self) -> str:
        try:
            ss = self.fetch_sunrise_sunset()
        except requests.exceptions.RequestException:
            return ""
        sunrise = ss.get("sunrise", "")
        sunset = ss.get("sunset", "")
        temp_part = ""
        w = self.fetch_weather_openweather()
        if w:
            temp = w.get("main", {}).get("temp")
            condition = ((w.get("weather") or [{}])[0].get("main") or "").strip()
            unit = "°C" if self.units == "metric" else ("°F" if self.units == "imperial" else "K")
            if temp is not None and condition:
                temp_part = f"Temp {temp}{unit}, {condition}."
            elif temp is not None:
                temp_part = f"Temp {temp}{unit}."
            elif condition:
                temp_part = f"{condition}."

        dt = core_time.local_dt()
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H:%M")
        day_name = dt.strftime("%A")  # Monday, Tuesday, ...
        day_type = core_time.weekday_label()  # weekday/weekend
        time_of_day = core_time.time_of_day_label(dt.hour)  # morning/afternoon/evening/night

        lines = [
            "Context update (time and environment):",
            f"Date: {date_str},",
            f"Day: {day_name} ({day_type}),",
            f"Time: {time_str}, it is ({time_of_day}).",
            f"Sunrise: {sunrise}",
            f"Sunset: {sunset}",
        ]
        if temp_part:
            lines.append(temp_part)
        return "\n".join(lines).strip()

    def weather_updater(self):
        if not self.should_update_now():
            return None
        text = self.build_injection_text()
        if not text or not text.strip():
            return None
        self.mark_updated()
        return text