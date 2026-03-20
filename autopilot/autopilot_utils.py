import core.timeutils as t
import json
import os


def default_settings():
    return {
        "state_dir": ".",
        "tick_every_seconds": 30,
        "jitter_min_ms": 10 * 1000,
        "jitter_max_ms": 2 * 60 * 1000,
        "addon_min_seconds": 30,
        "addon_max_seconds": 10 * 60,
        "cap_min": 0,
        "cap_max": 2,
        "quiet_start_hour": 23,
        "quiet_end_hour": 7,
        "reengage_min_hours": 4,
        "reengage_max_hours": 24,
        "addon_max_pending_inbound": 2,
        "addon_cooldown_minutes": 2,
        "addon_post_send_cooldown_minutes": 2,
        "starter_post_send_cooldown_minutes": 180
    }


def default_state():
    return {
        "paused": False,
        "debug_mode": False, # New field
        "last_inbound_ms": 0,
        "last_outbound_ms": 0,
        "last_inbound_text": "",
        "last_outbound_text": "",
        "next_eligible_send_ms": 0,
        "scheduled_send_ms": 0,
        "scheduled_kind": "",
        "last_activity_ms": 0,
        "pending_inbound_count": 0,
        "next_reengage_ms": 0,
        "last_autonomous_kind": "",
        "last_autonomous_ms": 0,
        "since_user_autonomous_count": 0,
        "since_user_autonomous_cap": 0,
        "last_introspection_ms": 0
    }


def load_state(state_dir, chat_id):
    path = os.path.join(state_dir, "user", "chats", str(chat_id), "state", "autopilot_state.json")
    if not os.path.exists(path):
        return default_state()
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        base = default_state()
        if isinstance(st, dict):
            base.update(st)
        return base
    except Exception as e:
        print(f"[load_state] failed to load {path}: {e}")
        return default_state()


def save_state(state_dir, chat_id, st):
    path = os.path.join(state_dir, "user", "chats", str(chat_id), "state", "autopilot_state.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)


def build_prompt(kind):
    dt = t.local_dt()
    date = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%H:%M")
    tod = t.time_of_day_label(dt.hour)
    wk = t.weekday_label()
    meta = (f"Meta: Local date {date}, local time {time_str}, {tod}, {wk}.\n"
            "Instruction: Be natural, conversational, and context-aware.\n")
    if kind == "addon":
        return (
            meta + "Task: Write ONE short add-on message.\n"
            "Rules: Keep it casual, natural. Do not sound formal. Do not over-explain.\n"
            "Avoid starting a new topic unless it's a light continuation.\n")

    if kind == "starter":
        return (
            meta + "Task: Start a fresh conversation with ONE short message.\n"
            "Rules: Do NOT reference old details unless explicitly relevant. Do not act like you're continuing yesterday.\n"
            "Make it sound like a normal person starting a new thread.\n")

    return meta + "Task: Write ONE short friendly message.\n"
