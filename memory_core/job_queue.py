import logging
import traceback

logger = logging.getLogger(__name__)

class JobQueue:
    def __init__(self, jobs: list):
        try:
            if not isinstance(jobs, list):
                raise TypeError("Jobs must be a list.")
            self.jobs = jobs
        except Exception as e:
            logger.error(f"Failed to initialize JobQueue: {e}")
            logger.error(traceback.format_exc())
            self.jobs = []

    def enqueue(self, job_type: str, payload: dict):
        try:
            job = {"type": job_type, "payload": payload}
            self.jobs.append(job)
        except Exception as e:
            logger.error(f"Failed to enqueue job: {e}")
            logger.error(traceback.format_exc())

    def enqueue_once(self, job_type: str, payload: dict):
        try:
            # Avoid duplicate jobs
            for job in self.jobs:
                if job.get("type") == job_type and job.get("payload") == payload:
                    return
            self.enqueue(job_type, payload)
        except Exception as e:
            logger.error(f"Failed to enqueue_once job: {e}")
            logger.error(traceback.format_exc())

    def pop_next(self):
        try:
            if not self.jobs:
                return None
            return self.jobs.pop(0)
        except Exception as e:
            logger.error(f"Failed to pop next job: {e}")
            logger.error(traceback.format_exc())
            return None

    def is_empty(self) -> bool:
        return not self.jobs
