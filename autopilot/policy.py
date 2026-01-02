import time as _time
from .timeutils import now_ms, local_hour, is_quiet_hours, jitter_ms, pseudo_random_range

def schedule_next_reengage(st, cfg):
    now = now_ms()
    min_ms = cfg["reengage_min_hours"] * 60 * 60 * 1000
    max_ms = cfg["reengage_max_hours"] * 60 * 60 * 1000

    delay = pseudo_random_range(min_ms, max_ms)
    target = now + delay

    lt = _time.localtime(target / 1000)
    hour = lt.tm_hour
    if is_quiet_hours(hour, cfg["quiet_start_hour"], cfg["quiet_end_hour"]):
        day_start = int(_time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)
        target = day_start + cfg["quiet_end_hour"] * 60 * 60 * 1000
        if target <= now:
            target += 24 * 60 * 60 * 1000

    st["next_reengage_ms"] = target

def roll_cap_on_inbound(st, cfg):
    st["since_user_autonomous_count"] = 0
    st["since_user_autonomous_cap"] = int(pseudo_random_range(cfg["cap_min"], cfg["cap_max"] + 1))

def can_send_autonomous(st, kind, cfg):
    if st.get("paused"):
        return False

    if is_quiet_hours(local_hour(), cfg["quiet_start_hour"], cfg["quiet_end_hour"]):
        return False

    if now_ms() < st.get("next_eligible_send_ms", 0):
        return False

    if kind != "starter":
        used = int(st.get("since_user_autonomous_count", 0))
        cap = int(st.get("since_user_autonomous_cap", 0))
        if used >= cap:
            return False

    return True

def maybe_schedule_addon_immediately(st, cfg, base_ms):
    if st.get("paused"):
        return
    if is_quiet_hours(local_hour(), cfg["quiet_start_hour"], cfg["quiet_end_hour"]):
        return
    used = int(st.get("since_user_autonomous_count", 0))
    cap = int(st.get("since_user_autonomous_cap", 0))
    if used >= cap:
        return
    if int(st.get("scheduled_send_ms", 0)) != 0:
        return
    base = base_ms + int(cfg["addon_min_seconds"] * 1000)
    st["scheduled_send_ms"] = base + jitter_ms(cfg["jitter_min_ms"], cfg["jitter_max_ms"])
    st["scheduled_kind"] = "addon"

def should_schedule_addon(chat_id, st, cfg):
    if not can_send_autonomous(st, "addon", cfg):
        return False

    if st.get("scheduled_send_ms", 0):
        return False

    if st.get("last_outbound_ms", 0) == 0:
        return False

    if int(st.get("pending_inbound_count", 0)) > cfg["addon_max_pending_inbound"]:
        return False

    if int(st.get("pending_inbound_count", 0)) != 0:
        return False

    t = now_ms()
    seconds_since_out = (t - st["last_outbound_ms"]) / 1000.0
    if seconds_since_out < cfg["addon_min_seconds"]:
        return False

    if seconds_since_out > cfg["addon_max_seconds"]:
        return False

    last_kind = st.get("last_autonomous_kind", "")
    last_auto_ms = int(st.get("last_autonomous_ms", 0))
    minutes_since_last_auto = (t - last_auto_ms) / 60000.0 if last_auto_ms else 9999
    if last_kind == "addon" and minutes_since_last_auto < cfg["addon_cooldown_minutes"]:
        return False

    return True

def should_schedule_starter(st, cfg):
    if not can_send_autonomous(st, "starter", cfg):
        return False

    if st.get("scheduled_send_ms", 0):
        return False

    if st.get("last_inbound_ms", 0) == 0:
        return False

    target = int(st.get("next_reengage_ms", 0))
    if target == 0:
        schedule_next_reengage(st, cfg)
        target = int(st.get("next_reengage_ms", 0))
    return now_ms() >= target

def schedule_addon(st, cfg):
    base = now_ms() + int(cfg["addon_min_seconds"] * 1000)
    st["scheduled_send_ms"] = base + jitter_ms(cfg["jitter_min_ms"], cfg["jitter_max_ms"])
    st["scheduled_kind"] = "addon"

def schedule_starter(st, cfg):
    st["scheduled_send_ms"] = now_ms() + jitter_ms(cfg["jitter_min_ms"], cfg["jitter_max_ms"])
    st["scheduled_kind"] = "starter"

def apply_post_send_updates(st, kind, cfg):
    t_ms = now_ms()
    st["last_outbound_ms"] = t_ms
    st["last_activity_ms"] = max(st.get("last_activity_ms", 0), t_ms)
    st["last_autonomous_kind"] = kind
    st["last_autonomous_ms"] = t_ms
    if kind == "addon":
        st["since_user_autonomous_count"] = int(st.get("since_user_autonomous_count", 0)) + 1
        st["next_eligible_send_ms"] = t_ms + int(cfg["addon_post_send_cooldown_minutes"] * 60 * 1000)
    else:
        st["next_eligible_send_ms"] = t_ms + int(cfg["starter_post_send_cooldown_minutes"] * 60 * 1000)
        schedule_next_reengage(st, cfg)