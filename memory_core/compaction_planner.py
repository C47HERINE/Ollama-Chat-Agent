from memory_core.job_queue import JobQueue


class CompactionPlanner:
    """
    Schedule jobs into state.jobs based on thresholds (does NOT run jobs).
    """

    def __init__(self, max_level_files: int, l0_max_msgs: int):
        self.max_level_files = int(max_level_files)
        self.l0_max_msgs = int(l0_max_msgs)

    def plan(self, st: dict, l0_count: int) -> dict:
        q = JobQueue(st.get("jobs", []))

        # Schedule when a level REACHES 3 (oldest two will be compacted when job runs)
        if len(st.get("l3_active", [])) >= self.max_level_files:
            q.enqueue_once("COMPACT_L3_TO_L4")
        if len(st.get("l2_active", [])) >= self.max_level_files:
            q.enqueue_once("COMPACT_L2_TO_L3")
        if len(st.get("l1_active", [])) >= self.max_level_files:
            q.enqueue_once("COMPACT_L1_TO_L2")

        # L0 job when it reaches 30
        if int(l0_count) >= self.l0_max_msgs:
            q.enqueue_once("COMPACT_L0_TO_L1")

        st["jobs"] = q.jobs
        return st
