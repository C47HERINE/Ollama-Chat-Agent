import datetime
import json


def core_log(event: str, **data):
    """
    Console log with timestamp + event name.
    """
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = f"[{ts}] {event}"
    if not data:
        print(prefix)
        return
    try:
        payload = json.dumps(data, ensure_ascii=False)
    except Exception:
        payload = str(data)
    print(f"{prefix} {payload}")
