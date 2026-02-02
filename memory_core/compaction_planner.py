import logging
import traceback

logger = logging.getLogger(__name__)

class CompactionPlanner:
    def __init__(self, max_level_files: int, l0_max_msgs: int):
        try:
            self.max_level_files = max_level_files
            self.l0_max_msgs = l0_max_msgs
        except Exception as e:
            logger.error(f"Failed to initialize CompactionPlanner: {e}")
            logger.error(traceback.format_exc())
            raise

    def plan(self, state: dict, l0_count: int) -> dict:
        try:
            if not isinstance(state, dict):
                logger.error("CompactionPlanner received invalid state (not a dict).")
                return {}

            if "jobs" not in state:
                state["jobs"] = []

            # Plan L0 -> L1 compaction
            if l0_count >= self.l0_max_msgs:
                # Check if a compaction job for L0 is already queued
                is_queued = any(job.get("type") == "COMPACT_L0_TO_L1" for job in state["jobs"])
                if not is_queued:
                    logger.info("Planning L0->L1 compaction job.")
                    state["jobs"].append({"type": "COMPACT_L0_TO_L1", "payload": {}})
            
            return state
        except Exception as e:
            logger.error(f"An error occurred during compaction planning: {e}")
            logger.error(traceback.format_exc())
            # Return the original state to avoid data loss
            return state if isinstance(state, dict) else {}
