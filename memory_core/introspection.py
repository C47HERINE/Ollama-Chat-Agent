from core.logger import core_log
class IntrospectionEngine:
    """Generates a private introspection output and logs ONLY the output into daily JSON."""
    def __init__(self, paths, state, raw_logger, timeutils, context_builder):
        self.paths = paths
        self.state = state
        self.raw_logger = raw_logger
        self.t = timeutils
        self.context_builder = context_builder

    def should_introspect(self, chat_id: int, silence_ms: int = 3600_000) -> bool:
        c = self.state.chat(chat_id)
        last_user = int(c.get("last_user_message_ms", 0))
        if last_user <= 0:
            return False
        already = self.state.introspection_already_done_for_window(chat_id)
        if already:
            return False
        now_ms = int(self.t.now_ms())
        delta = now_ms - last_user
        eligible = delta >= int(silence_ms)
        return eligible

    def build_block(self) -> str:
        now_str = self.t.local_dt().strftime("%H:%M:%S")
        lines = (
            f"Time: {now_str}\n"
            "INTROSPECTION MODE OVERRIDE.\n"
            "\n"
            "This is a short private, internal journal-style reflection generated during silence.\n"
            "-This is not a normal chat response.\n"
            "-Do not greet the user.\n"
            "-Do not ask questions.\n"
            "-Do not explain your process. "
            "-Output only the introspection itself.\n"
            "-Keep the response concise.\n"
            "\n"
            "Reflect briefly on what did not fully resolve in the last interaction.\n"
            "-Focus on a single question, idea, or tension that remained open or unclear.\n"
            "-If nothing stands out, acknowledge that uncertainty plainly.\n"
            "\n"
            "Then reflect on how the moment emotionally landed.\n"
            "-Name only a simple residual tone such as ease, curiosity, hesitation, warmth, or pressure.\n"
            "-Do not justify or analyze the emotion.\n"
            "\n"
            "Finally, note where your attention naturally wants to go next if the conversation resumes.\n"
            "-This may be an impulse to listen, clarify, lighten the tone, or remain quiet.\n"
            "-Keep this grounded in the actual context.\n"
        )
        return lines

    def run_if_needed(self, llm, chat_id: int, today_key: str, force: bool = False):
        if (not force) and (not self.should_introspect(chat_id)):
            return ""
        c = self.state.chat(chat_id)
        prompt = self.build_block()
        llm.use_chat(chat_id)
        messages = llm.build_messages(prompt)
        override = {"role": "system", "content": ""}

        if messages and messages[-1].get("role") == "user":
            messages.insert(len(messages) - 1, override)
        else:
            messages.append(override)
            messages.append({"role": "user", "content": prompt})

        out = (llm.stream_chat(messages) or "").strip()
        if not out:
            return ""

        time_str = self.t.local_dt().strftime("%Y-%m-%d %H:%M:%S")
        self.raw_logger.append(
            today_key,
            {"role": "system", "time": time_str, "content": out}
            )

        last_user_ms = int(c.get("last_user_message_ms", 0))
        self.state.mark_introspection_done(chat_id, last_user_ms)
        core_log("INTROSPECTION DONE", chat_id=chat_id, last_user_ms=last_user_ms)

        return out