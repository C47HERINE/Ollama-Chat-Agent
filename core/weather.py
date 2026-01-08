from dotenv import load_dotenv
import core.timeutils as core_time
import os, json, requests

load_dotenv()

class WeatherInjector:
    """Twice-daily background context injection (sunrise / sunset buckets)."""
    def __init__(self, state_dir="agent_state", state_file="weather_state.json"):
        self.state_dir = state_dir
        self.state_path = os.path.join(state_dir, state_file)
        os.makedirs(self.state_dir, exist_ok=True)

        self.lat = os.getenv("LAT")
        self.lon = os.getenv("LON")
        self.tz = os.getenv("TZ")
        self.units = os.getenv("UNITS") or "metric"
        self.api_key = os.getenv("OPENWEATHER_API_KEY")

        self.st = self.load_state()

    def load_state(self):
        default = {"last_by_bucket": {"sunrise": "", "sunset": ""}}
        if not os.path.exists(self.state_path):
            return default
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("last_by_bucket"), dict):
                lb = data["last_by_bucket"]
                return {
                    "last_by_bucket": {
                        "sunrise": str(lb.get("sunrise", "")),
                        "sunset": str(lb.get("sunset", "")),
                    }
                }
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return default

    def save_state(self):
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.st, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def should_update_now(self) -> bool:
        if not self.lat or not self.lon:
            return False
        bucket = core_time.daytime_bucket()
        if bucket == "none":
            return False
        today = core_time.today_key_local()
        last = (self.st.get("last_by_bucket", {}) or {}).get(bucket, "")
        return last != today

    def mark_updated(self):
        bucket = core_time.daytime_bucket()
        if bucket in ("sunrise", "sunset"):
            if "last_by_bucket" not in self.st or not isinstance(self.st["last_by_bucket"], dict):
                self.st["last_by_bucket"] = {"sunrise": "", "sunset": ""}
            self.st["last_by_bucket"][bucket] = core_time.today_key_local()
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
        except requests.exceptions.RequestException as e:
            core_log("WEATHER_FETCH_FAIL", error=str(e), source="sunrise-sunset")
            return ""
        sunrise = ss.get("sunrise", "")
        sunset = ss.get("sunset", "")
        temp_part = ""
        try:
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
        except requests.exceptions.RequestException as e:
            core_log("WEATHER_FETCH_FAIL", error=str(e), source="openweather")
            # keep sunrise/sunset even if openweather fails

        dt = core_time.local_dt()
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H:%M")
        lines = [
            f"Context update (environment): {date_str} {time_str} local.",
            f"Sunrise: {sunrise}",
            f"Sunset: {sunset}",
        ]
        if temp_part:
            lines.append(temp_part)
        return "\n".join(lines).strip()

    def maybe_inject(self, chat_id: int) -> str:
        """Returns injection text if due; otherwise ""."""
        if not self.should_update_now():
            core_log("WEATHER_SKIP", chat_id=chat_id)
            return ""

        text = self.build_injection_text()
        if not text:
            core_log("WEATHER_SKIP", chat_id=chat_id, reason="empty_text")
            return ""

        # Mark updated only if we actually produced an injection
        self.mark_updated()
        core_log("WEATHER_READY", chat_id=chat_id, chars=len(text))
        return text