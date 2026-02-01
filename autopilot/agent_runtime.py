from autopilot.prompts import build_prompt
import autopilot.policy as policy
import core.timeutils as t

class AgentRuntime:
    def __init__(self, autopilot, get_memory_manager, memory_manager, llm, telegram, voice):
        self.chat_id = None
        self.memory_manager = None
        self.autopilot = autopilot
        self.get_memory_manager = get_memory_manager
        self.llm = llm
        self.telegram = telegram
        self.voice = voice

    def get_chat_id(self):
        self.chat_id = self.autopilot.known_chats
        return self.chat_id

    def memory(self):
        self.get_chat_id()
        self.memory_manager = self.get_memory_manager(self.chat_id)
        return self.memory_manager

    def generate_fn(self, chat_id, prompt_text):
        self.memory()
        msgs = self.memory_manager(chat_id, prompt_text)
        return (self.llm.ask_messages(msgs, stream_to_console=False) or "").strip()

    def send_fn(self, chat_id, text_to_send):
        self.memory()
        self.memory_manager.on_message("assistant", text_to_send, kind="autopilot")
        kind, sent_text = self.voice.send(self.telegram, chat_id, text_to_send)
        self.autopilot.observe_outbound(chat_id, sent_text, cooldown_minutes=180, allow_addon=False)
        self.memory_manager.after_assistant_sent()

    def tick(self, send_fn, generate_fn):
        if t.now_s() < self.autopilot.next_tick_s:
            return False

        self.autopilot.next_tick_s = t.now_s() + self.autopilot.tick_every_seconds
        for chat_id in list(self.autopilot.known_chats):
            state = self.autopilot.load_state(chat_id)
            if state.get("scheduled_send_ms", 0) and t.now_ms() >= state["scheduled_send_ms"]:
                kind = state.get("scheduled_kind") or "starter"
                prompt = build_prompt(kind)
                state["scheduled_send_ms"] = 0
                state["scheduled_kind"] = ""
                text = (generate_fn(chat_id, prompt) or "").strip()
                if text:
                    send_fn(chat_id, text)
                    state["last_outbound_text"] = text
                    policy.apply_post_send_updates(state, kind, self.autopilot.config)
                self.autopilot.save_state(chat_id, state)
                continue
            if state.get("scheduled_send_ms", 0):
                self.autopilot.save_state(chat_id, state)
                continue
            if policy.should_schedule_addon(state, self.autopilot.config):
                policy.schedule_addon(state, self.autopilot.config)
                self.autopilot.save_state(chat_id, state)
                continue
            if policy.should_schedule_starter(state, self.autopilot.config):
                policy.schedule_starter(state, self.autopilot.config)
                self.autopilot.save_state(chat_id, state)
                continue
            self.autopilot.save_state(chat_id, state)
        return True