import os
from typing import List, Tuple
from core.logger import core_log
from memory_core.file_index import (
    list_daily_summaries,
    list_weekly_summaries,
    list_monthly_summaries,
    list_yearly_summaries,
)

class ContextBuilder:
    """Build runtime injection context with strict priority."""
    def __init__(self, paths, max_chars: int = 0):
        self.paths = paths
        # kept only for logging/compatibility; NOT enforced
        self.max_chars = int(max_chars or 0)

    # --- IMPORTANT: raw file reader (never parses JSON) ---
    def read_text_raw(self, path: str) -> str:
        """
        Read any file as plain text. No JSON parsing, no transformations.
        """
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            core_log("CTX_READ_FAIL", path=path, err=str(e))
            return ""

    def _format_file_block(self, filename: str, content: str) -> str:
        """
        Make each file self-contained and readable inside the final injected context.
        JSON files are wrapped as literal JSON text to reduce accidental instruction-following.
        """
        content = (content or "").strip()
        if not content:
            return ""

        lower = filename.lower()
        if lower.endswith(".json"):
            return f"### {filename}\n```json\n{content}\n```"
        else:
            return f"### {filename}\n{content}"

    def read_all_files_as_text(
        self,
        folder: str,
        exts: Tuple[str, ...] = (".md", ".txt", ".json"),
    ) -> Tuple[str, List[str]]:
        if not os.path.isdir(folder):
            return "", []

        parts: List[str] = []
        files: List[str] = []

        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if os.path.isfile(path) and name.lower().endswith(exts):
                files.append(name)
                raw = self.read_text_raw(path)
                block = self._format_file_block(name, raw)
                if block:
                    parts.append(block)

        return "\n\n".join(parts).strip(), files

    def build(self, today_key: str, yesterday_key: str) -> str:
        blocks: List[Tuple[str, str]] = []

        # 1) RAW CONTEXT first (highest priority): D0 then D1 (full files)
        d0_name = f"{today_key}.json"
        d1_name = f"{yesterday_key}.json"
        d0_path = os.path.join(self.paths.daily_raw_dir, d0_name)
        d1_path = os.path.join(self.paths.daily_raw_dir, d1_name)

        d0 = self.read_text_raw(d0_path).strip() if os.path.exists(d0_path) else ""
        d1 = self.read_text_raw(d1_path).strip() if os.path.exists(d1_path) else ""

        if d0:
            blocks.append(("RAW CONTEXT (D0)", self._format_file_block(d0_name, d0)))
        if d1:
            blocks.append(("RAW CONTEXT (D1)", self._format_file_block(d1_name, d1)))

        # 2) SYSTEM PROMPT (allow .json per your setup, but read as raw text)
        system_text, system_files = self.read_all_files_as_text(
            self.paths.system_prompt_dir,
            exts=(".md", ".txt", ".json"),
        )
        if system_text:
            blocks.append(("SYSTEM PROMPT", system_text))

        # 3) STATIC CONTEXT (allow .json per your setup, but read as raw text)
        static_text, static_files = self.read_all_files_as_text(
            self.paths.context_dir,
            exts=(".md", ".txt", ".json"),
        )
        if static_text:
            blocks.append(("STATIC CONTEXT", static_text))

        # 4) CARRY SUMMARIES (lowest priority overall)
        #    (these are typically .md/.txt, but we still read raw to be safe)
        daily = list_daily_summaries(self.paths.daily_summary_dir)
        weekly = list_weekly_summaries(self.paths.weekly_summary_dir)
        monthly = list_monthly_summaries(self.paths.monthly_summary_dir)
        yearly = list_yearly_summaries(self.paths.yearly_summary_dir)

        carry_selected = {}

        def add_carry(title: str, path: str):
            txt = (self.read_text_raw(path) or "").strip()
            if txt:
                blocks.append((title, txt))

        if daily:
            carry_selected["daily"] = daily[-1].path
            add_carry("CARRY DAILY (latest)", daily[-1].path)
        if weekly:
            carry_selected["weekly"] = weekly[-1].path
            add_carry("CARRY WEEKLY (latest)", weekly[-1].path)
        if monthly:
            carry_selected["monthly"] = monthly[-1].path
            add_carry("CARRY MONTHLY (latest)", monthly[-1].path)
        if yearly:
            carry_selected["yearly"] = yearly[-1].path
            add_carry("CARRY YEARLY (latest)", yearly[-1].path)

        # Format blocks (no truncation)
        formatted: List[str] = []
        for title, txt in blocks:
            txt = (txt or "").strip()
            if not txt:
                continue
            formatted.append(f"## {title}\n{txt}\n")

        return "\n".join(formatted).strip()
