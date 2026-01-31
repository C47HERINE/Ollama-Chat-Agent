import json
import os


def default_state():
    return {
        "paused": False,
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
        "last_introspection_ms": 0,
    }


def state_path(root_dir, chat_id):
    return os.path.join(root_dir, "user", "chats", str(chat_id), "state", "autopilot_state.json")


def load_state(state_dir, chat_id):
    path = state_path(state_dir, chat_id)
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
    path = state_path(state_dir, chat_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)
