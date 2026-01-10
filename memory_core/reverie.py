# memory_core/reverie.py
import os
import random
from typing import List, Optional, Dict

from core.logger import core_log  # <-- event logger
from memory_core.file_index import (
    list_daily_summaries,
    list_weekly_summaries,
    list_monthly_summaries,
    list_yearly_summaries,
    read_text,
)


class ReveriePicker:
    """Weighted random selection of an older summary file for introspection reverie."""
    def __init__(self, paths):
        self.paths = paths

    def _pick_tier(self, avail: List[str]) -> str:
        weights = {"daily": 0.50, "weekly": 0.25, "monthly": 0.15, "yearly": 0.10}
        pool = [(t, float(weights.get(t, 0.0))) for t in avail]
        total = sum(w for _, w in pool) or 1.0
        r = random.random() * total
        acc = 0.0
        for t, w in pool:
            acc += w
            if r <= acc:
                return t
        chosen = avail[0]
        return chosen

    def pick_file(self) -> Optional[str]:
        c = self._candidates()
        tiers = [t for t, files in c.items() if files]

        if not tiers:
            return None

        tier = self._pick_tier(tiers)
        files = c[tier]

        # Tier-specific biasing
        if tier == "daily":
            # keys are YYYY-MM-DD. list_* returns sorted oldest->newest.
            if len(files) > 7:
                chosen = random.choice(files[:-7])
                return chosen.path
            chosen = random.choice(files)
            return chosen.path

        # weekly/monthly/yearly: prefer older half if possible
        if len(files) > 2:
            half = files[: max(1, len(files) // 2)]
            chosen = random.choice(half)
            return chosen.path

        chosen = random.choice(files)
        return chosen.path

    def reverie_block(self) -> str:
        path = self.pick_file()
        if not path:
            return "REVERIE: none available"
        content = read_text(path).rstrip()
        return "\n".join(
            [
                "note: this is a fleeting personal recollection, not a conclusion or analysis. ",
                "It may be incomplete, emotionally biased, or only loosely connected to recent events. ",
                "Treat this as something remembered, not something reasoned. ",
                "",
                "BEGIN_REVERIE_FILE",
                content,
                "END_REVERIE_FILE",
            ]
        )