import logging
import traceback

logger = logging.getLogger(__name__)


class CompactionPlanner:
    """Plan background memory compaction jobs based on active L0 message count."""

    def __init__(self, l0_max_messages: int):
        self.l0_max_messages = int(l0_max_messages)

    def plan(self, state: dict, l0_count: int) -> dict:
        """Ensure the compaction queue contains a single L0->L1 job when threshold is reached."""
        try:
            if not isinstance(state, dict):
                logger.error("CompactionPlanner received invalid state (not a dict).")
                return {}

            jobs = state.setdefault("jobs", [])
            if l0_count < self.l0_max_messages:
                return state

            already_queued = any(job.get("type") == "COMPACT_L0_TO_L1" for job in jobs)
            if not already_queued:
                logger.info("Planning L0->L1 compaction job.")
                jobs.append({"type": "COMPACT_L0_TO_L1", "payload": {}})
            return state
        except Exception as error:
            logger.error(f"An error occurred during compaction planning: {error}")
            logger.error(traceback.format_exc())
            return state if isinstance(state, dict) else {}
