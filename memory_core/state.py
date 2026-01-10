import json
import os
from typing import Any, Dict


class StateManager:
    """Persistent state for timers, flags, and per-chat bookkeeping."""

    def __init__(self, state_path: str):
        self.state_path = state_path
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        self.data = self.load()

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_path):
            return {"global": {}, "chats": {}}
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                d.setdefault("global", {})
                d.setdefault("chats", {})
                return d
        except Exception:
            pass
        return {"global": {}, "chats": {}}

    def save(self):
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def chat(self, chat_id: int) -> Dict[str, Any]:
        chats = self.data.setdefault("chats", {})
        key = str(chat_id)
        if key not in chats or not isinstance(chats[key], dict):
            chats[key] = {
                "last_user_message_ms": 0,
                "last_user_message_text": "",
                "introspection_done_for_user_ms": 0,
            }
        return chats[key]

    def set_last_user_message(self, chat_id: int, ms: int, text: str):
        c = self.chat(chat_id)
        c["last_user_message_ms"] = int(ms)
        c["last_user_message_text"] = (text or "")
        self.save()

    def mark_introspection_done(self, chat_id: int, user_ms: int):
        c = self.chat(chat_id)
        c["introspection_done_for_user_ms"] = int(user_ms)
        self.save()

    def introspection_already_done_for_window(self, chat_id: int) -> bool:
        c = self.chat(chat_id)
        return int(c.get("introspection_done_for_user_ms", 0)) == int(c.get("last_user_message_ms", 0))