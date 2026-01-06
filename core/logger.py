# core/logger.py
import json
from datetime import datetime
import os

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def core_log(event: str, **data):
    """
    Console log with timestamp + event name.
    Keeps payload short and machine-readable.
    """
    prefix = f"[{_ts()}] {event}"
    if not data:
        print(prefix)
        return
    # keep it compact
    try:
        payload = json.dumps(data, ensure_ascii=False)
    except Exception:
        payload = str(data)
    print(f"{prefix} {payload}")

def env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")