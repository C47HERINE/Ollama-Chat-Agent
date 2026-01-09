import os
from memory_core.job_queue import JobQueue
from memory_core.helpers import read_text, write_text, render_chat_as_text
from memory_core.recap_store import RecapStore

class CompactionRunner:
    """
    Run EXACTLY ONE job (highest priority) per call.
    Designed to be called AFTER assistant sends.
    """
    def __init__(self, paths, state_store, conv_buf, summarizer):
        self.paths = paths
        self.state_store = state_store
        self.conv = conv_buf
        self.summarizer = summarizer

    def _load_master(self) -> str:
        if not os.path.exists(self.paths.master_path()):
            return ""
        return read_text(self.paths.master_path()).strip()

    def _save_master(self, text: str) -> None:
        write_text(self.paths.master_path(), (text or "").strip())

    def _level_store(self, level: int) -> RecapStore:
        if level == 1:
            return RecapStore(self.paths.l1_dir)
        if level == 2:
            return RecapStore(self.paths.l2_dir)
        if level == 3:
            return RecapStore(self.paths.l3_dir)
        raise ValueError("level must be 1..3")

    def run_one(self) -> bool:
        st = self.state_store.load()
        q = JobQueue(st.get("jobs", []))
        job = q.pop_next()

        if not job:
            st["jobs"] = q.jobs
            self.state_store.save(st)
            return False

        jtype = job.get("type", "")

        # Preconditions to avoid overflowing the next level.
        # If blocked, requeue current job and ensure higher-level job exists.
        if jtype == "COMPACT_L0_TO_L1" and len(st["l1_active"]) >= 3:
            q.enqueue_once("COMPACT_L1_TO_L2")
            q.jobs.append(job)
            st["jobs"] = q.jobs
            self.state_store.save(st)
            return False

        if jtype == "COMPACT_L1_TO_L2" and len(st["l2_active"]) >= 3:
            q.enqueue_once("COMPACT_L2_TO_L3")
            q.jobs.append(job)
            st["jobs"] = q.jobs
            self.state_store.save(st)
            return False

        if jtype == "COMPACT_L2_TO_L3" and len(st["l3_active"]) >= 3:
            q.enqueue_once("COMPACT_L3_TO_L4")
            q.jobs.append(job)
            st["jobs"] = q.jobs
            self.state_store.save(st)
            return False

        # ---- Execute ONE job ----
        if jtype == "COMPACT_L3_TO_L4":
            if len(st["l3_active"]) < 2:
                # nothing to do
                st["jobs"] = q.jobs
                self.state_store.save(st)
                return False

            a, b = st["l3_active"][0], st["l3_active"][1]
            l3_store = self._level_store(3)
            a_txt, b_txt = l3_store.read(a), l3_store.read(b)

            master = self._load_master()
            master_new = self.summarizer.l3_to_l4_master(master, a_txt, b_txt)
            self._save_master(master_new)

            # remove the oldest two; newest (and any beyond) remains as buffer
            st["l3_active"] = st["l3_active"][2:]

        elif jtype == "COMPACT_L2_TO_L3":
            if len(st["l2_active"]) < 2:
                st["jobs"] = q.jobs
                self.state_store.save(st)
                return False

            a, b = st["l2_active"][0], st["l2_active"][1]
            l2_store = self._level_store(2)
            a_txt, b_txt = l2_store.read(a), l2_store.read(b)

            merged = self.summarizer.merge_two(a_txt, b_txt)
            l3_store = self._level_store(3)
            out = l3_store.write_new("l3", merged)

            st["l2_active"] = st["l2_active"][2:]
            st["l3_active"].append(out)

        elif jtype == "COMPACT_L1_TO_L2":
            if len(st["l1_active"]) < 2:
                st["jobs"] = q.jobs
                self.state_store.save(st)
                return False

            a, b = st["l1_active"][0], st["l1_active"][1]
            l1_store = self._level_store(1)
            a_txt, b_txt = l1_store.read(a), l1_store.read(b)

            merged = self.summarizer.merge_two(a_txt, b_txt)
            l2_store = self._level_store(2)
            out = l2_store.write_new("l2", merged)

            st["l1_active"] = st["l1_active"][2:]
            st["l2_active"].append(out)

        elif jtype == "COMPACT_L0_TO_L1":
            # pop oldest 20 and keep last 10 in active.json
            chunk = self.conv.pop_oldest(20)
            if not chunk:
                st["jobs"] = q.jobs
                self.state_store.save(st)
                return False

            self.conv.archive_many(chunk)
            chunk_txt = render_chat_as_text(chunk)

            recap = self.summarizer.l0_to_l1(chunk_txt)
            l1_store = self._level_store(1)
            out = l1_store.write_new("l1", recap)

            st["l1_active"].append(out)

        # Save updated state (job already removed by pop_next)
        st["jobs"] = q.jobs
        self.state_store.save(st)
        return True