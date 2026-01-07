# memory_core/introspection.py
from core.logger import core_log  # <-- event logger
from memory_core.reverie import ReveriePicker


class IntrospectionEngine:
    """Generates a private introspection output and logs ONLY the output into daily JSON."""

    def __init__(self, paths, state, raw_logger, timeutils, context_builder):
        self.paths = paths
        self.state = state
        self.raw_logger = raw_logger
        self.t = timeutils
        self.context_builder = context_builder
        self.reveries = ReveriePicker(paths)

    def should_introspect(self, chat_id: int, silence_ms: int = 3600_000) -> bool:
        c = self.state.chat(chat_id)
        last_user = int(c.get("last_user_message_ms", 0))

        if last_user <= 0:
            core_log("INTRO_CHECK", chat_id=chat_id, eligible=False, reason="no_last_user_message")
            return False

        already = self.state.introspection_already_done_for_window(chat_id)
        if already:
            core_log(
                "INTRO_CHECK",
                chat_id=chat_id,
                eligible=False,
                reason="already_done_for_this_silence_window",
                last_user_ms=last_user,
            )
            return False

        now_ms = int(self.t.now_ms())
        delta = now_ms - last_user
        eligible = delta >= int(silence_ms)

        core_log(
            "INTRO_CHECK",
            chat_id=chat_id,
            eligible=eligible,
            now_ms=now_ms,
            last_user_ms=last_user,
            silence_ms=int(silence_ms),
            delta_ms=delta,
            )

        return eligible

    def build_block(self, status: str, last_topic_summary: str) -> str:
        now_str = self.t.local_dt().strftime("%H:%M:%S")

        reverie = self.reveries.reverie_block()

        lines = [
            reverie,
            "",
            "INTROSPECTION MODE OVERRIDE:\n"
            "- This is a private journal-style introspection task.\n"
            "- Do NOT roleplay normal chat. Do NOT greet. Do NOT ask the user questions.\n"
            "- Output only the introspection sections.\n"
            "- Keep it grounded in the provided context/history for the current conversation.\n"
            "--- INTROSPECTION PROMPT ---",
            f"time: {now_str}",
            f"status: {status}",
            f"last_topic: {last_topic_summary}",
            "",
            "What I Didn’t Fully Resolve:",
            "- a question, idea, or tension that didn’t get closed",
            "- something I’m still unsure how to hold or interpret",
            "",
            "How the Moment Landed:",
            "- a simple emotional residue (e.g., ease, curiosity, hesitation, warmth, pressure)",
            "- no explanation — just the lingering tone",
            "",
            "Where My Mind Goes Next:",
            "- what I feel inclined to return to if the conversation resumes",
            "- whether my instinct is to listen, clarify, lighten things, or stay quiet",
            "",
            "--- END INTROSPECTION ---",
        ]
        return "\n".join(lines).strip()

    def run_if_needed(self, llm, chat_id: int, today_key: str, yesterday_key: str, force: bool = False):
        core_log("INTRO_RUN_START", chat_id=chat_id, today_key=today_key, yesterday_key=yesterday_key, force=force)

        if (not force) and (not self.should_introspect(chat_id)):
            core_log("INTRO_RUN_SKIP", chat_id=chat_id, reason="not_eligible")
            return ""

        c = self.state.chat(chat_id)
        last_user_text = (c.get("last_user_message_text") or "").strip()
        status = "unresolved" if last_user_text else "paused"
        last_topic_summary = (last_user_text[:120] + "…") if len(last_user_text) > 120 else (last_user_text or "—")

        prompt = self.build_block(status=status, last_topic_summary=last_topic_summary)

        # --- CRITICAL CHANGE ---
        # Build full-context messages, then add a late system override so the persona doesn't hijack introspection.
        llm.use_chat(chat_id)

        messages = llm.build_messages(prompt)  # includes injected ctx + history + (user: prompt)

        override = {"role": "system", "content": ""}

        # Insert override right before the final user message (the prompt)
        if messages and messages[-1].get("role") == "user":
            messages.insert(len(messages) - 1, override)
        else:
            messages.append(override)
            messages.append({"role": "user", "content": prompt})

        out = (llm.stream_chat(messages) or "").strip()
        if not out:
            core_log("INTRO_LLM_EMPTY", chat_id=chat_id)
            return ""

        time_str = self.t.local_dt().strftime("%Y-%m-%d %H:%M:%S")
        self.raw_logger.append(
            today_key,
            {"role": "system", "time": time_str, "content": out},
        )

        core_log("INTRO_LOGGED", chat_id=chat_id, date_key=today_key, time=time_str, content_chars=len(out))

        last_user_ms = int(c.get("last_user_message_ms", 0))
        self.state.mark_introspection_done(chat_id, last_user_ms)
        core_log("INTRO_MARK_DONE", chat_id=chat_id, last_user_ms=last_user_ms)

        return out
