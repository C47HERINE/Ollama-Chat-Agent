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

    def _candidates(self) -> Dict[str, list]:
        daily = list_daily_summaries(self.paths.daily_summary_dir)
        weekly = list_weekly_summaries(self.paths.weekly_summary_dir)
        monthly = list_monthly_summaries(self.paths.monthly_summary_dir)
        yearly = list_yearly_summaries(self.paths.yearly_summary_dir)

        core_log("REVERIE_CANDIDATES",
                 daily=len(daily), weekly=len(weekly), monthly=len(monthly), yearly=len(yearly))
        return {
            "daily": daily,
            "weekly": weekly,
            "monthly": monthly,
            "yearly": yearly,
            }

    def _pick_tier(self, avail: List[str]) -> str:
        weights = {"daily": 0.50, "weekly": 0.25, "monthly": 0.15, "yearly": 0.10}
        pool = [(t, float(weights.get(t, 0.0))) for t in avail]
        total = sum(w for _, w in pool) or 1.0
        r = random.random() * total
        acc = 0.0
        for t, w in pool:
            acc += w
            if r <= acc:
                core_log("REVERIE_TIER_PICK", chosen=t, avail=avail, weights=weights)
                return t
        chosen = avail[0]
        core_log("REVERIE_TIER_PICK_FALLBACK", chosen=chosen, avail=avail, weights=weights)
        return chosen

    def pick_file(self) -> Optional[str]:
        c = self._candidates()
        tiers = [t for t, files in c.items() if files]

        if not tiers:
            core_log("REVERIE_PICK_NONE", reason="no_summary_files")
            return None

        tier = self._pick_tier(tiers)
        files = c[tier]

        # Tier-specific biasing
        if tier == "daily":
            # keys are YYYY-MM-DD. list_* returns sorted oldest->newest.
            if len(files) > 7:
                chosen = random.choice(files[:-7])
                core_log(
                    "REVERIE_PICK_FILE",
                    tier=tier,
                    bias="older_than_last_7_days",
                    chosen_key=chosen.key,
                    chosen_path=chosen.path,
                    pool_size=len(files),
                    considered=len(files[:-7]),
                )
                return chosen.path
            chosen = random.choice(files)
            core_log(
                "REVERIE_PICK_FILE",
                tier=tier,
                bias="no_older_than_7_available",
                chosen_key=chosen.key,
                chosen_path=chosen.path,
                pool_size=len(files),
            )
            return chosen.path

        # weekly/monthly/yearly: prefer older half if possible
        if len(files) > 2:
            half = files[: max(1, len(files) // 2)]
            chosen = random.choice(half)
            core_log(
                "REVERIE_PICK_FILE",
                tier=tier,
                bias="older_half",
                chosen_key=chosen.key,
                chosen_path=chosen.path,
                pool_size=len(files),
                considered=len(half),
            )
            return chosen.path

        chosen = random.choice(files)
        core_log(
            "REVERIE_PICK_FILE",
            tier=tier,
            bias="no_half_possible",
            chosen_key=chosen.key,
            chosen_path=chosen.path,
            pool_size=len(files),
        )
        return chosen.path

    def reverie_block(self) -> str:
        path = self.pick_file()
        if not path:
            core_log("REVERIE_BLOCK", chosen_path=None, result="none_available")
            return "REVERIE: none available"

        content = read_text(path).rstrip()

        core_log(
            "REVERIE_BLOCK",
            chosen_path=path,
            chosen_bytes=len(content.encode("utf-8", errors="ignore")),
            chosen_chars=len(content),
        )

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