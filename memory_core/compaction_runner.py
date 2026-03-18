import os
import json
import time
import traceback
import logging
from .helpers import render_chat_as_text, write_text, read_json, write_json
from .job_queue import JobQueue

logger = logging.getLogger(__name__)

class CompactionRunner:
    def __init__(self, paths, state_store, conversation_buffer, summarizer, vector_manager, l0_summary_msgs: int):
        self.paths = paths
        self.state_store = state_store
        self.conversation = conversation_buffer
        self.summarizer = summarizer
        self.vector_manager = vector_manager
        self.l0_summary_msgs = int(l0_summary_msgs)

    def run_one(self) -> bool:
        try:
            state = self.state_store.load()
            queue = JobQueue(state.get("jobs", []))
            job = queue.pop_next()

            if not job:
                return False

            logger.info(f"Executing job: {job.get('type')}")
            job_type = job.get("type", "")

            if job_type == "COMPACT_L0_TO_L1":
                self._run_l0_compaction(job, queue)
            elif job_type == "UPDATE_MASTER":
                self._run_master_update(job)

            state["jobs"] = queue.jobs
            self.state_store.save(state)
            return True
        except Exception as e:
            logger.error(f"An unexpected error occurred in CompactionRunner.run_one: {e}")
            logger.error(traceback.format_exc())
            return False

    def _run_l0_compaction(self, job, queue):
        chunk = self.conversation.pop_oldest(self.l0_summary_msgs)
        if not chunk:
            logger.warning("L0 compaction job failed: No messages to compact.")
            return

        self.conversation.archive_many(chunk)
        chunk_txt = render_chat_as_text(chunk)

        try:
            l1_data = self.summarizer.l0_to_l1(chunk_txt)
            if not l1_data or (not l1_data.get("diary") and not l1_data.get("bullets")):
                logger.warning("Summarizer returned empty data. Saving failed chunk.")
                self._save_failed_chunk(chunk_txt)
                return

            l1_id = f"l1_{int(time.time())}"
            l1_data["id"] = l1_id
            l1_data["timestamp"] = str(time.time())
            
            path = os.path.join(self.paths.l1_dir, f"{l1_id}.json")
            write_json(path, l1_data, indent=4)
            
            state = self.state_store.load()
            if "l1_active" not in state: state["l1_active"] = []
            state["l1_active"].append(l1_id)
            self.state_store.save(state)
            
            logger.info(f"Summarization successful for {l1_id}")
            
            bullets = l1_data.get("bullets", [])
            if bullets:
                self.vector_manager.add_to_index(bullets, l1_id)

            queue.enqueue_once("UPDATE_MASTER", {"l1_id": l1_id})

        except Exception as e:
            logger.error(f"Failed during L0 compaction: {e}")
            logger.error(traceback.format_exc())
            self._save_failed_chunk(chunk_txt)

    def _run_master_update(self, job):
        l1_id = job.get("payload", {}).get("l1_id")
        if not l1_id:
            logger.warning("UPDATE_MASTER failed: No l1_id provided.")
            return

        try:
            l1_path = os.path.join(self.paths.l1_dir, f"{l1_id}.json")
            master_path = self.paths.master_path()
            
            l1_data = read_json(l1_path)
            master_data = read_json(master_path) or {}
            
            if not l1_data:
                logger.warning(f"UPDATE_MASTER failed: Could not read {l1_id}.")
                return

            logger.info(f"Updating Master Record with {l1_id}...")
            diary = l1_data.get("diary", "")
            rules_locked = l1_data.get("rules_locked", [])
            
            new_master = self.summarizer.update_master(master_data, diary, rules_locked)
            if new_master:
                new_master["last_updated"] = str(time.time())
                write_json(master_path, new_master, indent=4)
                logger.info("Master Record updated.")
            else:
                logger.warning("Master Update failed: LLM returned empty.")
        except Exception as e:
            logger.error(f"Failed during master update for L1 ID {l1_id}: {e}")
            logger.error(traceback.format_exc())

    def _save_failed_chunk(self, chunk_text):
        try:
            failed_path = os.path.join(self.paths.l1_dir, f"failed_chunk_{int(time.time())}.txt")
            write_text(failed_path, chunk_text)
            logger.info(f"Saved failed chunk to {failed_path}")
        except Exception as e:
            logger.error(f"Could not save failed chunk: {e}")
            logger.error(traceback.format_exc())
