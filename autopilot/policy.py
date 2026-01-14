import core.timeutils as t


def schedule_next_reengage(state, config):
    now = t.now_ms()
    min_ms = config["reengage_min_hours"] * 60 * 60 * 1000
    max_ms = config["reengage_max_hours"] * 60 * 60 * 1000
    delay = t.pseudo_random_range(min_ms, max_ms)
    target = now + delay
    lt = t.time.localtime(target / 1000)
    hour = lt.tm_hour
    if t.is_quiet_hours(hour, config["quiet_start_hour"], config["quiet_end_hour"]):
        day_start = int(t.time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)
        target = day_start + config["quiet_end_hour"] * 60 * 60 * 1000
        if target <= now:
            target += 24 * 60 * 60 * 1000
    state["next_reengage_ms"] = target


def roll_cap_on_inbound(state, config):
    state["since_user_autonomous_count"] = 0
    state["since_user_autonomous_cap"] = int(
        t.pseudo_random_range(config["cap_min"], config["cap_max"] + 1))


def can_send_autonomous(state, kind, config):
    if state.get("paused"):
        return False
    if t.is_quiet_hours(t.local_dt().hour, config["quiet_start_hour"], config["quiet_end_hour"]):
        return False
    if t.now_ms() < state.get("next_eligible_send_ms", 0):
        return False
    if kind != "starter":
        used = int(state.get("since_user_autonomous_count", 0))
        cap = int(state.get("since_user_autonomous_cap", 0))
        if used >= cap:
            return False
    return True


def maybe_schedule_addon_immediately(state, cfg, base_ms):
    if state.get("paused"):
        return
    if t.is_quiet_hours(t.local_dt().hour, cfg["quiet_start_hour"], cfg["quiet_end_hour"]):
        return
    used = int(state.get("since_user_autonomous_count", 0))
    cap = int(state.get("since_user_autonomous_cap", 0))
    if used >= cap:
        return
    if int(state.get("scheduled_send_ms", 0)) != 0:
        return
    base = base_ms + int(cfg["addon_min_seconds"] * 1000)
    state["scheduled_send_ms"] = base + t.jitter_ms(cfg["jitter_min_ms"], cfg["jitter_max_ms"])
    state["scheduled_kind"] = "addon"


def should_schedule_addon(st, cfg):
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

    now = t.now_ms()
    seconds_since_out = (now - st["last_outbound_ms"]) / 1000.0
    if seconds_since_out < cfg["addon_min_seconds"]:
        return False

    if seconds_since_out > cfg["addon_max_seconds"]:
        return False

    last_kind = st.get("last_autonomous_kind", "")
    last_auto_ms = int(st.get("last_autonomous_ms", 0))
    minutes_since_last_auto = (now - last_auto_ms) / 60000.0 if last_auto_ms else 9999
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
    return t.now_ms() >= target


def schedule_addon(st, cfg):
    base = t.now_ms() + int(cfg["addon_min_seconds"] * 1000)
    st["scheduled_send_ms"] = base + t.jitter_ms(cfg["jitter_min_ms"], cfg["jitter_max_ms"])
    st["scheduled_kind"] = "addon"


def schedule_starter(st, cfg):
    st["scheduled_send_ms"] = t.now_ms() + t.jitter_ms(cfg["jitter_min_ms"], cfg["jitter_max_ms"])
    st["scheduled_kind"] = "starter"


def apply_post_send_updates(st, kind, cfg):
    sent_ms = t.now_ms()
    st["last_outbound_ms"] = sent_ms
    st["last_activity_ms"] = max(st.get("last_activity_ms", 0), sent_ms)
    st["last_autonomous_kind"] = kind
    st["last_autonomous_ms"] = sent_ms
    if kind == "addon":
        st["since_user_autonomous_count"] = int(st.get("since_user_autonomous_count", 0)) + 1
        st["next_eligible_send_ms"] = sent_ms + int(cfg["addon_post_send_cooldown_minutes"] * 60 * 1000)
    else:
        st["next_eligible_send_ms"] = sent_ms + int(cfg["starter_post_send_cooldown_minutes"] * 60 * 1000)
        schedule_next_reengage(st, cfg)
