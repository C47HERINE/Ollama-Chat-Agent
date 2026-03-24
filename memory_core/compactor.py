import os
import time
from .helpers import render_chat_as_text, write_text, read_json, write_json, read_all

class MemoryCompactor:
    """Plan and run memory compaction jobs."""

    def __init__(self,
        paths,
        state_store,
        summarizer,
        vector_manager,
        l0_summary_msgs: int,
        max_level_files: int,
        l0_max_msgs: int):
        self.paths = paths
        self.state_store = state_store
        self.summarizer = summarizer
        self.vector_manager = vector_manager
        self.l0_summary_msgs = int(l0_summary_msgs)
        self.max_level_files = max_level_files
        self.l0_max_msgs = l0_max_msgs
        self.jobs = []
        self.active_path = self.paths.l0_active_path()
        self.archive_path = self.paths.l0_archive_path


    def pop_oldest(self, count: int) -> list:
        try:
            current_data = read_all(self.active_path)
            if len(current_data) < count:
                return []
            to_pop = current_data[:count]
            remaining = current_data[count:]
            write_json(self.active_path, remaining)
            return to_pop
        except Exception as e:
            print(e)
            return []


    def archive_many(self, items: list):
        if not items:
            return
        # Read existing archive, append new items, and write back
        archive_data = read_json(self.archive_path) or []
        archive_data.extend(items)
        write_json(self.archive_path, archive_data)


    def load_jobs(self, state: dict) -> None:
        stored_jobs = state.get("jobs", [])
        self.jobs = stored_jobs if isinstance(stored_jobs, list) else []


    def save_jobs(self, state: dict) -> None:
        state["jobs"] = self.jobs


    def enqueue_once(self, job_type: str, payload: dict) -> None:
        for queued_job in self.jobs:
            if queued_job.get("type") == job_type and queued_job.get("payload") == payload:
                return
        self.jobs.append({"type": job_type, "payload": payload})


    def plan(self, state: dict, l0_message_count) -> dict:
        try:
            if not isinstance(state, dict):
                return {}
            self.load_jobs(state)
            if l0_message_count >= self.l0_max_msgs:
                self.enqueue_once("COMPACT_L0_TO_L1", {})
            state["jobs"] = self.jobs
            return state
        except Exception as error:
            print("MemoryCompactor | plan |", error)
            return state if isinstance(state, dict) else {}


    def compact_once(self) -> bool:
        try:
            state = self.state_store.load()
            self.load_jobs(state)
            next_job = self.jobs.pop(0) if self.jobs else None
            if not next_job:
                return False
            job_type = next_job.get("type", "")
            if job_type == "COMPACT_L0_TO_L1":
                self.run_l0_compaction()
            elif job_type == "UPDATE_MASTER":
                self.run_master_update(next_job)
            state["jobs"] = self.jobs
            self.state_store.save(state)
            return True
        except Exception as error:
            print("MemoryCompactor | compact_once |", error)
            return False


    def run_l0_compaction(self) -> None:
        message_chunk = self.pop_oldest(self.l0_summary_msgs)
        if not message_chunk:
            return
        self.archive_many(message_chunk)
        chunk_text = render_chat_as_text(message_chunk)
        try:
            l1_summary = self.summarizer.l0_to_l1(chunk_text)
            if not l1_summary or (not l1_summary.get("diary") and not l1_summary.get("bullets")):
                self.save_failed_chunk(chunk_text)
                return
            l1_id = f"l1_{int(time.time())}"
            l1_summary["id"] = l1_id
            l1_summary["timestamp"] = str(time.time())
            l1_path = os.path.join(self.paths.l1_dir, f"{l1_id}.json")
            write_json(l1_path, l1_summary, indent=4)
            state = self.state_store.load()
            state.setdefault("l1_active", [])
            state["l1_active"].append(l1_id)
            self.state_store.save(state)
            bullet_points = l1_summary.get("bullets", [])
            if bullet_points:
                self.vector_manager.add_to_index(bullet_points, l1_id)
            self.enqueue_once("UPDATE_MASTER", {"l1_id": l1_id})
        except Exception as error:
            print("MemoryCompactor | run_l0_compaction |", error)
            self.save_failed_chunk(chunk_text)


    def run_master_update(self, job: dict) -> None:
        l1_id = job.get("payload", {}).get("l1_id")
        if not l1_id:
            return
        l1_path = os.path.join(self.paths.l1_dir, f"{l1_id}.json")
        master_path = self.paths.master_path()
        l1_summary = read_json(l1_path)
        master_summary = read_json(master_path) or {}
        if not l1_summary:
            return
        diary_text = l1_summary.get("diary", "")
        core_principles = l1_summary.get("core_principles", [])
        if not core_principles:
            core_principles = l1_summary.get("rules_locked", [])
        updated_master = self.summarizer.update_master(master_summary, diary_text, core_principles)
        if updated_master:
            updated_master["last_updated"] = str(time.time())
            write_json(master_path, updated_master, indent=4)


    def save_failed_chunk(self, chunk_text: str) -> None:
        failed_chunk_path = os.path.join(
            self.paths.l1_dir, f"failed_chunk_{int(time.time())}.txt")
        write_text(failed_chunk_path, chunk_text)
