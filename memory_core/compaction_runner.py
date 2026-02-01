import os
import json
import time
from .helpers import render_chat_as_text
from .job_queue import JobQueue

class CompactionRunner:
    """
    Runs the L0->L1 compaction job.
    """
    def __init__(self, paths, state_store, conversation_buffer, summarizer, l0_summary_msgs: int):
        self.paths = paths
        self.state_store = state_store
        self.conversation = conversation_buffer
        self.summarizer = summarizer
        self.l0_summary_msgs = int(l0_summary_msgs)

    def run_one(self) -> bool:
        state = self.state_store.load()
        queue = JobQueue(state.get("jobs", []))
        job = queue.pop_next()

        if not job:
            # No jobs to run
            return False

        print(f"[CompactionRunner] Executing job: {job.get('type')}")
        job_type = job.get("type", "")

        if job_type == "COMPACT_L0_TO_L1":
            chunk = self.conversation.pop_oldest(self.l0_summary_msgs)
            if not chunk:
                print("[CompactionRunner] Job failed: No messages to compact.")
                state["jobs"] = queue.jobs
                self.state_store.save(state)
                return False

            self.conversation.archive_many(chunk)
            chunk_txt = render_chat_as_text(chunk)

            try:
                l1_data = self.summarizer.l0_to_l1(chunk_txt)
                
                if not l1_data or (not l1_data.get("diary_entry") and not l1_data.get("bullets")):
                    print(f"    - WARNING: Summarizer returned empty data for chunk. Skipping.")
                else:
                    l1_id = f"l1_{int(time.time())}"
                    l1_data["id"] = l1_id
                    l1_data["timestamp"] = str(time.time())
                    
                    path = os.path.join(self.paths.l1_dir, f"{l1_id}.json")
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(l1_data, f, indent=2)
                    
                    if "l1_active" not in state: state["l1_active"] = []
                    state["l1_active"].append(l1_id)
                    print(f"[CompactionRunner] Created new L1 summary: {l1_id}")

            except Exception as e:
                print(f"[CompactionRunner] Failed to process L1 JSON from LLM: {e}")

        # Save updated state (job already removed by pop_next)
        state["jobs"] = queue.jobs
        self.state_store.save(state)
        return True
