from .job_queue import JobQueue

class CompactionPlanner:
    """
    Schedules L0->L1 compaction jobs when the active conversation buffer is full.
    """
    def __init__(self, max_level_files: int, l0_max_msgs: int):
        self.l0_max_msgs = int(l0_max_msgs)

    def plan(self, st: dict, l0_count: int) -> dict:
        q = JobQueue(st.get("jobs", []))
        
        if int(l0_count) >= self.l0_max_msgs:
            q.enqueue_once("COMPACT_L0_TO_L1")

        st["jobs"] = q.jobs
        return st
