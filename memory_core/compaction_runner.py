import os

from memory_core.helpers import read_text, render_chat_as_text, write_text
from memory_core.job_queue import JobQueue
from memory_core.recap_store import RecapStore


class CompactionRunner:
    """
    Run EXACTLY ONE job (highest priority) per call.
    Designed to be called AFTER assistant sends.
    """

    def __init__(self, paths, state_store, conversation_buffer, summarizer, l0_summary_msgs: int):
        self.paths = paths
        self.state_store = state_store
        self.conversation = conversation_buffer
        self.summarizer = summarizer
        self.l0_summary_msgs = int(l0_summary_msgs)

    def _load_master(self) -> str:
        if not os.path.exists(self.paths.master_path()):
            return ""
        else:
            return read_text(self.paths.master_path())

    def _save_master(self, text: str) -> None:
        write_text(self.paths.master_path(), (text or ""))

    def _level_store(self, level: int) -> RecapStore:
        if level == 1:
            return RecapStore(self.paths.l1_dir)
        if level == 2:
            return RecapStore(self.paths.l2_dir)
        if level == 3:
            return RecapStore(self.paths.l3_dir)
        raise ValueError("level must be 1..3")

    def run_one(self) -> bool:
        state = self.state_store.load()
        queue = JobQueue(state.get("jobs", []))
        job = queue.pop_next()

        if not job:
            state["jobs"] = queue.jobs
            self.state_store.save(state)
            return False

        job_type = job.get("type", "")

        if job_type == "COMPACT_L0_TO_L1" and len(state["l1_active"]) >= 3:
            queue.enqueue_once("COMPACT_L1_TO_L2")
            queue.jobs.append(job)
            state["jobs"] = queue.jobs
            self.state_store.save(state)
            return False

        if job_type == "COMPACT_L1_TO_L2" and len(state["l2_active"]) >= 3:
            queue.enqueue_once("COMPACT_L2_TO_L3")
            queue.jobs.append(job)
            state["jobs"] = queue.jobs
            self.state_store.save(state)
            return False

        if job_type == "COMPACT_L2_TO_L3" and len(state["l3_active"]) >= 3:
            queue.enqueue_once("COMPACT_L3_TO_L4")
            queue.jobs.append(job)
            state["jobs"] = queue.jobs
            self.state_store.save(state)
            return False

        if job_type == "COMPACT_L3_TO_L4":
            if len(state["l3_active"]) < 2:
                state["jobs"] = queue.jobs
                self.state_store.save(state)
                return False

            a, b = state["l3_active"][0], state["l3_active"][1]
            l3_store = self._level_store(3)
            a_txt, b_txt = l3_store.read(a), l3_store.read(b)

            master = self._load_master()
            master_new = self.summarizer.l3_to_l4_master(master, a_txt, b_txt)
            self._save_master(master_new)
            state["l3_active"] = state["l3_active"][2:]

        elif job_type == "COMPACT_L2_TO_L3":
            if len(state["l2_active"]) < 2:
                state["jobs"] = queue.jobs
                self.state_store.save(state)
                return False

            a, b = state["l2_active"][0], state["l2_active"][1]
            l2_store = self._level_store(2)
            a_txt, b_txt = l2_store.read(a), l2_store.read(b)

            merged = self.summarizer.merge_two(a_txt, b_txt)
            l3_store = self._level_store(3)
            out = l3_store.write_new("l3", merged)

            state["l2_active"] = state["l2_active"][2:]
            state["l3_active"].append(out)

        elif job_type == "COMPACT_L1_TO_L2":
            if len(state["l1_active"]) < 2:
                state["jobs"] = queue.jobs
                self.state_store.save(state)
                return False

            a, b = state["l1_active"][0], state["l1_active"][1]
            l1_store = self._level_store(1)
            a_txt, b_txt = l1_store.read(a), l1_store.read(b)

            merged = self.summarizer.merge_two(a_txt, b_txt)
            l2_store = self._level_store(2)
            out = l2_store.write_new("l2", merged)

            state["l1_active"] = state["l1_active"][2:]
            state["l2_active"].append(out)

        elif job_type == "COMPACT_L0_TO_L1":
            chunk = self.conversation.pop_oldest(self.l0_summary_msgs)
            if not chunk:
                state["jobs"] = queue.jobs
                self.state_store.save(state)
                return False

            self.conversation.archive_many(chunk)
            chunk_txt = render_chat_as_text(chunk)

            recap = self.summarizer.l0_to_l1(chunk_txt)
            l1_store = self._level_store(1)
            out = l1_store.write_new("l1", recap)

            state["l1_active"].append(out)

        state["jobs"] = queue.jobs
        self.state_store.save(state)
        return True
