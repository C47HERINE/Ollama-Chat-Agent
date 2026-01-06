# memory_core/introspection.py
from core.logger import core_log  # <-- event logger
from memory_core.reverie import ReveriePicker


class IntrospectionEngine:
    """Generates the required introspection block and logs it into daily JSON (never sent)."""

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

        core_log(
            "INTRO_BUILD_START",
            local_time=now_str,
            status=status,
            last_topic_summary_preview=(last_topic_summary[:120] if last_topic_summary else ""),
            last_topic_summary_len=len(last_topic_summary or ""),
        )

        reverie = self.reveries.reverie_block()

        core_log(
            "INTRO_BUILD_REVERIE_READY",
            reverie_present=(reverie != "REVERIE: none available"),
            reverie_chars=len(reverie or ""),
        )

        lines = [
            reverie,
            "",
            "--- INTROSPECTION ---",
            f"time: {now_str}",
            "note: private, subjective reflection during silence; incomplete and non-authoritative",
            "",
            "What Stayed With Me:",
            "- one concrete moment, phrase, or exchange from earlier that keeps resurfacing",
            "- something small that felt heavier or more meaningful than expected",
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

        block = "\n".join(lines)

        core_log("INTRO_BUILD_DONE", block_chars=len(block), block_lines=len(lines))
        return block

    def run_if_needed(self, chat_id: int, today_key: str, yesterday_key: str):
        # yesterday_key is currently unused here, but kept for signature stability
        core_log("INTRO_RUN_START", chat_id=chat_id, today_key=today_key, yesterday_key=yesterday_key)

        if not self.should_introspect(chat_id):
            core_log("INTRO_RUN_SKIP", chat_id=chat_id, reason="not_eligible")
            return ""

        c = self.state.chat(chat_id)
        last_user_text = (c.get("last_user_message_text") or "").strip()
        status = "unresolved" if last_user_text else "paused"
        last_topic_summary = (
            (last_user_text[:120] + "…") if len(last_user_text) > 120 else (last_user_text or "—")
        )

        core_log(
            "INTRO_RUN_ELIGIBLE",
            chat_id=chat_id,
            status=status,
            last_user_text_len=len(last_user_text),
            last_user_ms=int(c.get("last_user_message_ms", 0)),
        )

        block = self.build_block(status=status, last_topic_summary=last_topic_summary)

        # Log to daily JSON using the same schema
        time_str = self.t.local_dt().strftime("%Y-%m-%d %H:%M:%S")
        self.raw_logger.append(
            today_key,
            {
                "role": "system",
                "time": time_str,
                "content": block,
            },
        )

        core_log(
            "INTRO_LOGGED",
            chat_id=chat_id,
            date_key=today_key,
            time=time_str,
            role="system",
            content_chars=len(block),
        )

        # Mark done for this silence window
        last_user_ms = int(c.get("last_user_message_ms", 0))
        self.state.mark_introspection_done(chat_id, last_user_ms)

        core_log(
            "INTRO_MARK_DONE",
            chat_id=chat_id,
            last_user_ms=last_user_ms,
        )

        return block