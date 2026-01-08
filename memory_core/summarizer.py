import memory_core.file_index as file_index
from typing import List
import json, os

class Summarizer:
    """Hierarchical summarization engine. No reveries. Input files are never deleted."""
    def __init__(self, paths, timeutils):
        self.paths = paths
        self.t = timeutils

    def write_summary(self, out_path: str, text: str):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")

    def file_exists(self, path: str) -> bool:
        return os.path.exists(path)

    def read_daily_raw_as_text(self, raw_path: str) -> str:
        """Convert daily JSON conversation list into a compact text source for summarization."""
        if not os.path.exists(raw_path):
            return ""
        raw_txt = file_index.read_text(raw_path).strip()
        if not raw_txt:
            return ""
        try:
            data = json.loads(raw_txt)
            if not isinstance(data, list):
                return ""
            lines = []
            for m in data:
                if not isinstance(m, dict):
                    continue
                role = (m.get("role") or "").strip()
                time_s = (m.get("time") or "").strip()
                content = m.get("content")
                if content is None:
                    content = ""
                content = str(content).strip()

                if role not in ("user", "assistant", "system"):
                    continue
                if not content:
                    continue

                if time_s:
                    lines.append(f"[{time_s}] {role}: {content}")
                else:
                    lines.append(f"{role}: {content}")

            return "\n".join(lines).strip()
        except Exception:
            return (
                "NOTE: daily_raw JSON could not be parsed. Using raw file text as SOURCE.\n"
                "------ RAW DAILY FILE START ------\n"
                f"{raw_txt}\n"
                "------ RAW DAILY FILE END ------"
            ).strip()

    def build_prompt(self, period: str, source_text: str) -> str:
        return (
            "You are a memory writer producing a durable context file for future conversations.\n"
            "This is NOT a technical status report.\n"
            "Write like a person remembering the day clearly and in detail, while staying strictly faithful to the SOURCE.\n"
            "Do not invent. Do not infer facts that are not explicitly in the SOURCE.\n"
            "If something is unclear or missing, say 'unknown' or 'not stated'.\n\n"

            "CORE GOAL:\n"
            "- Preserve the specific things that should still be remembered weeks later: names, nicknames, roles, preferences,\n"
            "  relationship dynamics, boundaries, running jokes, recurring themes, new rules, and meaningful moments.\n"
            "- Bugs/debugging are included ONLY if they caused a behavior change, created a rule, or became a notable memory moment.\n\n"

            "ANTI-ROBOT RULES (very important):\n"
            "- Do NOT use report language: avoid words/phrases like 'system', 'module', 'identified', 'implementation', 'operational stability',\n"
            "  'numerous', 'various', 'significant push', 'marked by', 'centered on', 'persistent errors' unless you immediately name concrete examples.\n"
            "- Every bullet must contain at least ONE concrete anchor:\n"
            "  * an exact phrase that was said (short quote fragment, <= 12 words), OR\n"
            "  * a specific rule/format agreed, OR\n"
            "  * a named thing (feature name, tag, folder/file name, nickname, tool), OR\n"
            "  * a specific action taken (changed X, added Y, removed Z).\n"
            "- Prefer 'I remember...' / 'We...' / 'You...' framing instead of detached narration.\n"
            "- Keep it human and plainspoken. No corporate tone.\n"
            "- Keep roughly the same length as the example (short context file, not an essay).\n\n"

            "REVERIE / FEELING RULES:\n"
            "- Human-feeling language is allowed everywhere, but it must be grounded in the SOURCE.\n"
            "- Do not claim emotions unless the SOURCE implies them (e.g., frustration, excitement, relief).\n"
            "- Introspection can be warmer and more personal, but still must not invent events.\n\n"

            "OUTPUT FORMAT (follow exactly):\n"
            f"=== {period} MEMORY ===\n"
            "1) Snapshot\n"
            "- 1–3 sentences, first-person, plain language: what the day was really about.\n\n"

            "2) What Actually Happened (chronological)\n"
            "- Bullet list, chronological order.\n"
            "- Each bullet must include at least one concrete anchor (quote fragment / rule / named thing / action).\n"
            "- Prefer many smaller bullets over a few vague ones.\n\n"

            "3) What Felt Important (memory-weighted)\n"
            "- Bullet list of the moments that should carry forward (identity, names, nicknames, preferences, boundaries, story beats).\n"
            "- Each bullet MUST include:\n"
            "  * Why it matters long-term (one short clause), AND\n"
            "  * A concrete anchor from the SOURCE (quote fragment / rule / named thing / logged event).\n\n"

            "4) Agreements / Rules Locked In\n"
            "- Bullet list of explicit rules/conventions established (format, tags, scheduling, naming, priorities).\n"
            "- Each bullet must be written as a rule statement.\n\n"

            "5) Introspection (human memory tone)\n"
            "- One short paragraph.\n"
            "- Write like a person remembering: 'I remember...' / 'It stuck with me...' / 'The thing I don’t want to lose is...'\n"
            "- No analysis jargon (avoid: 'pattern', 'alignment', 'coherence', 'the model', 'the system').\n"
            "- Must remain faithful to SOURCE; if feelings are not supported, say 'I can’t tell from the log'.\n\n"

            "6) Open Threads (only real ones)\n"
            "- Bullet list of unresolved items explicitly present in the SOURCE.\n"
            "- No speculative TODOs.\n\n"

            "SOURCE:\n"
            f"{source_text}\n"
            )

    def llm_summary_text(self, llm, chat_id: int, prompt: str) -> str:
        llm.use_chat(chat_id)
        return (llm.ask(prompt, stream_to_console=False) or "").strip()

    def join_sources(self, paths: List[str]) -> str:
        parts = []
        for p in paths:
            if not p:
                continue
            if not os.path.exists(p):
                continue
            txt = file_index.read_text(p).strip()
            if txt:
                parts.append(txt)
        return "\n\n".join(parts).strip()

    def daily(self, llm, chat_id: int, day_key: str, raw_path: str, out_path: str) -> str:
        """Create daily summary for a specific day_key, from its daily_raw file."""
        if self.file_exists(out_path):
            return ""
        if not os.path.exists(raw_path):
            return ""
        src = self.read_daily_raw_as_text(raw_path)
        if not src.strip():
            return ""
        prompt = self.build_prompt(period=day_key, source_text=src)
        s = self.llm_summary_text(llm, chat_id, prompt)
        if not s:
            return ""
        self.write_summary(out_path, s)
        return out_path

    def weekly_range(self, llm, chat_id: int, start_key: str, end_key: str,
                     daily_paths: List[str], out_path: str) -> str:
        """Build a weekly summary from explicit daily summary files."""
        if self.file_exists(out_path):
            return ""
        if not daily_paths:
            return ""

        src = self.join_sources(daily_paths)
        if not src.strip():
            return ""

        period = f"{start_key} → {end_key}"
        prompt = self.build_prompt(period=period, source_text=src)
        s = self.llm_summary_text(llm, chat_id, prompt)
        if not s:
            return ""
        self.write_summary(out_path, s)
        return out_path

    def monthly_range(self, llm, chat_id: int, year: int, month: int,
                      daily_paths: List[str], out_path: str) -> str:
        """Build a monthly summary from explicit daily summary files within that month."""
        if self.file_exists(out_path):
            return ""
        if not daily_paths:
            return ""

        src = self.join_sources(daily_paths)
        if not src.strip():
            return ""

        period = f"{year:04d}-{month:02d}"
        prompt = self.build_prompt(period=period, source_text=src)
        s = self.llm_summary_text(llm, chat_id, prompt)
        if not s:
            return ""
        self.write_summary(out_path, s)
        return out_path

    def yearly_range(self, llm, chat_id: int, year: int, monthly_paths: List[str], out_path: str) -> str:
        """Build a yearly summary from explicit monthly summary files within that year."""
        if self.file_exists(out_path):
            return ""
        if not monthly_paths:
            return ""

        src = self.join_sources(monthly_paths)
        if not src.strip():
            return ""

        period = f"{year:04d}"
        prompt = self.build_prompt(period=period, source_text=src)
        s = self.llm_summary_text(llm, chat_id, prompt)
        if not s:
            return ""
        self.write_summary(out_path, s)
        return out_path