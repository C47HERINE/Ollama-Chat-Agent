import time

def now_ms():
    return int(time.time() * 1000)

def local_time():
    return time.localtime()

def local_hour():
    return local_time().tm_hour

def is_quiet_hours(hour, quiet_start_hour, quiet_end_hour):
    return hour >= quiet_start_hour or hour < quiet_end_hour

def time_of_day_label(hour):
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"

def weekday_label():
    w = local_time().tm_wday
    return "weekend" if w >= 5 else "weekday"

def jitter_ms(jitter_min_ms, jitter_max_ms):
    t = time.time()
    frac = t - int(t)   # 0..1
    return int(jitter_min_ms + frac * (jitter_max_ms - jitter_min_ms))

def pseudo_random_range(min_v, max_v):
    t = time.time()
    frac = t - int(t)
    return int(min_v + frac * (max_v - min_v))