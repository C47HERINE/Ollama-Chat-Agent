import time
from datetime import datetime, timedelta, timezone


LOCAL_OFFSET = -time.timezone if (time.localtime().tm_isdst == 0) else -time.altzone
LOCAL_TZ = timezone(timedelta(seconds=LOCAL_OFFSET))


def now_ms() -> int:
    """Return current epoch time in milliseconds."""
    return int(time.time() * 1000)


def local_dt() -> datetime:
    """Return OS-local datetime (timezone-aware)."""
    return datetime.now(LOCAL_TZ)


def local_dt_from_ms(ms: int) -> datetime:
    """Convert epoch ms to OS-local datetime (timezone-aware)."""
    return datetime.fromtimestamp(ms / 1000, LOCAL_TZ)


def weekday_label() -> str:
    """Return weekday/weekend label from OS-local date."""
    return "weekend" if local_dt().weekday() >= 5 else "weekday"


def time_of_day_label(hour: int) -> str:
    """Return morning/afternoon/evening/night label."""
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def jitter_ms(min_ms: int, max_ms: int) -> int:
    """Return deterministic jitter in milliseconds."""
    frac = time.time() % 1
    return int(min_ms + frac * (max_ms - min_ms))


def pseudo_random_range(min_v: int, max_v: int) -> int:
    """Return deterministic pseudo-random integer in range."""
    frac = time.time() % 1
    return int(min_v + frac * (max_v - min_v))
