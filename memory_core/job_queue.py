class JobQueue:
    """
    Manage a persistent list of jobs with priority order.
    """

    PRIORITY = {
        "COMPACT_L3_TO_L4": 1,
        "COMPACT_L2_TO_L3": 2,
        "COMPACT_L1_TO_L2": 3,
        "COMPACT_L0_TO_L1": 4,
    }

    def __init__(self, jobs_list: list):
        self.jobs = jobs_list if isinstance(jobs_list, list) else []

    def has(self, job_type: str) -> bool:
        return any(j.get("type") == job_type for j in self.jobs)

    def enqueue_once(self, job_type: str) -> None:
        if not self.has(job_type):
            self.jobs.append({"type": job_type})

    def pop_next(self):
        if not self.jobs:
            return None
        self.jobs.sort(key=lambda j: self.PRIORITY.get(j.get("type", ""), 999))
        return self.jobs.pop(0)
