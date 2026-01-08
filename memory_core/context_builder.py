import os
from typing import List, Tuple
from core.logger import core_log
from memory_core.file_index import (
    list_daily_summaries,
    list_weekly_summaries,
    list_monthly_summaries,
    list_yearly_summaries,
    read_text,
    )

class ContextBuilder:
    """Build runtime injection context with strict priority."""
    def __init__(self, paths, max_chars: int = 0):
        self.paths = paths
        # kept only for logging/compatibility; NOT enforced
        self.max_chars = int(max_chars or 0)

    def read_all_files_as_text(
        self, folder: str, exts: Tuple[str, ...] = (".md", ".txt", ".json"),) -> Tuple[str, List[str]]:
        if not os.path.isdir(folder):
            return "", []
        parts: List[str] = []
        files: List[str] = []
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if os.path.isfile(path) and name.lower().endswith(exts):
                files.append(name)
                parts.append(read_text(path).strip())
        return "\n\n".join(p for p in parts if p), files

    def build(self, today_key: str, yesterday_key: str) -> str:
        blocks: List[Tuple[str, str]] = []

        # 1) RAW CONTEXT first (highest priority): D0 then D1 (full files)
        d0_path = os.path.join(self.paths.daily_raw_dir, f"{today_key}.json")
        d1_path = os.path.join(self.paths.daily_raw_dir, f"{yesterday_key}.json")
        d0 = read_text(d0_path).strip() if os.path.exists(d0_path) else ""
        d1 = read_text(d1_path).strip() if os.path.exists(d1_path) else ""

        if d0:
            blocks.append(("RAW CONTEXT (D0)", d0))
        if d1:
            blocks.append(("RAW CONTEXT (D1)", d1))

        # 2) SYSTEM PROMPT (allow .json per your setup)
        system_text, system_files = self.read_all_files_as_text(
            self.paths.system_prompt_dir, exts=(".md", ".txt", ".json")
            )

        if system_text.strip():
            blocks.append(("SYSTEM PROMPT", system_text.strip()))

        # 3) STATIC CONTEXT (allow .json per your setup)
        static_text, static_files = self.read_all_files_as_text(
            self.paths.context_dir, exts=(".md", ".txt", ".json")
            )

        if static_text.strip():
            blocks.append(("STATIC CONTEXT", static_text.strip()))

        # 4) CARRY SUMMARIES (lowest priority overall)
        #    Order inside carry bucket: daily > weekly > monthly > yearly
        #    Each tier: latest first (currently you take only the latest)
        daily = list_daily_summaries(self.paths.daily_summary_dir)
        weekly = list_weekly_summaries(self.paths.weekly_summary_dir)
        monthly = list_monthly_summaries(self.paths.monthly_summary_dir)
        yearly = list_yearly_summaries(self.paths.yearly_summary_dir)
        carry_selected = {}
        if daily:
            carry_selected["daily"] = daily[-1].path
            txt = read_text(daily[-1].path).strip()
            if txt:
                blocks.append(("CARRY DAILY (latest)", txt))
        if weekly:
            carry_selected["weekly"] = weekly[-1].path
            txt = read_text(weekly[-1].path).strip()
            if txt:
                blocks.append(("CARRY WEEKLY (latest)", txt))
        if monthly:
            carry_selected["monthly"] = monthly[-1].path
            txt = read_text(monthly[-1].path).strip()
            if txt:
                blocks.append(("CARRY MONTHLY (latest)", txt))
        if yearly:
            carry_selected["yearly"] = yearly[-1].path
            txt = read_text(yearly[-1].path).strip()
            if txt:
                blocks.append(("CARRY YEARLY (latest)", txt))
        core_log("CTX_CARRY_SELECTED", **(carry_selected or {"none": True}))

        # Format blocks (no truncation)
        formatted: List[str] = []
        for title, txt in blocks:
            txt = (txt or "").strip()
            if not txt:
                continue
            formatted.append(f"## {title}\n{txt}\n")
        joined = "\n".join(formatted).strip()
        return joined