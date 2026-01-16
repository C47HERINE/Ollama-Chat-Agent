import os
import core.timeutils as t

from . import policy, state
from .config import default_settings
from .prompts import build_prompt


class AutoPilot:
    def __init__(self, tick_every_seconds=30, state_dir=None):
        self.config = default_settings()
        self.config["tick_every_seconds"] = tick_every_seconds
        if state_dir is not None:
            self.config["state_dir"] = state_dir
        self.tick_every_seconds = tick_every_seconds
        self.state_dir = self.config["state_dir"]
        self.known_chats = set()
        self.next_tick_s = t.now_s() + tick_every_seconds

        os.makedirs(self.state_dir, exist_ok=True)

    def reset_state(self, chat_id):
        st = state.default_state()
        self.save_state(chat_id, st)
        return st

    def load_state(self, chat_id):
        return state.load_state(self.state_dir, chat_id)

    def save_state(self, chat_id, st):
        state.save_state(self.state_dir, chat_id, st)

    def register_chat(self, chat_id):
        self.known_chats.add(chat_id)

    def observe_inbound(self, chat_id, text):
        self.register_chat(chat_id)
        _state = self.load_state(chat_id)
        policy.roll_cap_on_inbound(_state, self.config)
        ms = t.now_ms()
        _state["last_inbound_ms"] = ms
        _state["last_inbound_text"] = text
        _state["last_activity_ms"] = max(_state.get("last_activity_ms", 0), ms)
        _state["scheduled_send_ms"] = 0
        _state["scheduled_kind"] = ""
        _state["pending_inbound_count"] = int(_state.get("pending_inbound_count", 0)) + 1
        policy.schedule_next_reengage(_state, self.config)
        self.save_state(chat_id, _state)

    def observe_outbound(self, chat_id, text, cooldown_minutes=60, allow_addon=False):
        self.register_chat(chat_id)
        _state = self.load_state(chat_id)
        ms = t.now_ms()
        _state["last_outbound_ms"] = ms
        _state["last_outbound_text"] = text
        _state["last_activity_ms"] = max(_state.get("last_activity_ms", 0), ms)
        _state["pending_inbound_count"] = 0
        _state["next_eligible_send_ms"] = ms + int(cooldown_minutes * 60 * 1000)
        if allow_addon:
            policy.maybe_schedule_addon_immediately(_state, self.config, base_ms=ms)
        self.save_state(chat_id, _state)

    def format_status(self, chat_id):
        st = self.load_state(chat_id)
        now = t.now_ms()

        def fmt_ms(ts):
            if not ts:
                return "—"
            dt = t.local_dt_from_ms(ts)
            return dt.strftime("%Y-%m-%d %H:%M:%S")

        def age_minutes(ts):
            if not ts:
                return None
            return int((now - ts) / 60000)

        def in_minutes(ts):
            if not ts:
                return None
            return int((ts - now) / 60000)

        paused = st.get("paused", False)
        used = int(st.get("since_user_autonomous_count", 0))
        cap = int(st.get("since_user_autonomous_cap", 0))
        scheduled_ms = int(st.get("scheduled_send_ms", 0))
        scheduled_kind = st.get("scheduled_kind", "") or "—"
        reengage_ms = int(st.get("next_reengage_ms", 0))
        last_in_ms = int(st.get("last_inbound_ms", 0))
        last_out_ms = int(st.get("last_outbound_ms", 0))
        next_eligible_ms = int(st.get("next_eligible_send_ms", 0))
        pending = int(st.get("pending_inbound_count", 0))

        lines = [
            "AutoPilot status",
            f"Paused: {paused}",
            f"Autonomous since your last message: {used}/{cap}",
            f"Pending inbound count: {pending}",
            "",
            "Timing",
        ]
        li = age_minutes(last_in_ms)
        lo = age_minutes(last_out_ms)
        lines.append(
            f"Last inbound: {fmt_ms(last_in_ms)}" + (f" ({li} min ago)" if li is not None else "")
        )
        lines.append(
            f"Last outbound: {fmt_ms(last_out_ms)}" + (f" ({lo} min ago)" if lo is not None else "")
        )

        if scheduled_ms:
            mins = in_minutes(scheduled_ms)
            lines.append(
                f"Scheduled: {scheduled_kind} at {fmt_ms(scheduled_ms)}"
                + (f" (in ~{mins} min)" if mins is not None else "")
            )
        else:
            lines.append("Scheduled: —")

        if reengage_ms:
            mins = in_minutes(reengage_ms)
            lines.append(
                f"Next re-engage target: {fmt_ms(reengage_ms)}"
                + (f" (in ~{mins} min)" if mins is not None else "")
            )
        else:
            lines.append("Next re-engage target: —")

        if next_eligible_ms and next_eligible_ms > now:
            mins = in_minutes(next_eligible_ms)
            lines.append(
                f"Next eligible autonomous send: {fmt_ms(next_eligible_ms)} (in ~{mins} min)"
            )
        else:
            lines.append("Next eligible autonomous send: now")
        return "\n".join(lines)

    def tick(self, send_fn, generate_fn):
        if t.now_s() < self.next_tick_s:
            return False
        self.next_tick_s = t.now_s() + self.tick_every_seconds

        for chat_id in list(self.known_chats):
            _state = self.load_state(chat_id)
            if _state.get("scheduled_send_ms", 0) and t.now_ms() >= _state["scheduled_send_ms"]:
                kind = _state.get("scheduled_kind") or "starter"
                prompt = build_prompt(kind)

                _state["scheduled_send_ms"] = 0
                _state["scheduled_kind"] = ""
                text = (generate_fn(chat_id, prompt) or "").strip()
                if text:
                    send_fn(chat_id, text)
                    _state["last_outbound_text"] = text
                    policy.apply_post_send_updates(_state, kind, self.config)
                self.save_state(chat_id, _state)
                continue
            if _state.get("scheduled_send_ms", 0):
                self.save_state(chat_id, _state)
                continue
            if policy.should_schedule_addon(_state, self.config):
                policy.schedule_addon(_state, self.config)
                self.save_state(chat_id, _state)
                continue
            if policy.should_schedule_starter(_state, self.config):
                policy.schedule_starter(_state, self.config)
                self.save_state(chat_id, _state)
                continue

            self.save_state(chat_id, _state)

        return True
