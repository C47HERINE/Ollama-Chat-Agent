import os
import traceback

from .compaction_planner import CompactionPlanner
from .compaction_runner import CompactionRunner
from .conversation_buffer import ConversationBuffer
from .helpers import read_json, read_text, write_json
from .integrity_manager import MemoryIntegrityManager
from .paths import MemoryPaths
from .prompt_builder import PromptBuilder
from .prompt_library import PromptLibrary
from .state_store import StateStore
from .summarizer import Summarizer
from .vector_manager import VectorManager


class MemoryManager:
    """Owns the end-to-end memory lifecycle for a single chat."""

    def __init__(self, root: str, chat_id: int, config_path: str, prompts_path: str, llm):
        try:
            self.paths = MemoryPaths(root=root, chat_id=chat_id)
            self.paths.ensure()

            self.config = read_json(config_path)
            if not isinstance(self.config, dict):
                raise RuntimeError("memory_config.json must be a JSON object")

            self.vector_manager = VectorManager(collection_name=f"chat_{chat_id}")
            self._reset_vector_collection_if_new_chat()

            self.state_store = StateStore(self.paths.state_path())
            self.state_store.ensure_exists()

            if not os.path.exists(self.paths.l0_active_path()):
                write_json(self.paths.l0_active_path(), [])

            self.conversation = ConversationBuffer(
                self.paths.l0_active_path(),
                self.paths.l0_archive_path(),
            )

            prompts = PromptLibrary(prompts_path)
            system_prompt = read_text(os.path.join(self.paths.system_dir, "system_prompt.txt")) or ""

            summarizer = Summarizer(prompt_lib=prompts, llm=llm, system_prompt=system_prompt)
            self.planner = CompactionPlanner(l0_max_messages=int(self.config.get("l0", {}).get("max_msgs")))
            self.runner = CompactionRunner(
                self.paths,
                self.state_store,
                self.conversation,
                summarizer,
                self.vector_manager,
                l0_summary_msgs=int(self.config.get("l0", {}).get("summary_msgs")),
            )

            self.integrity_manager = MemoryIntegrityManager(self.paths.l1_dir, self.vector_manager)
            self.prompt_builder = PromptBuilder(self.paths, self.vector_manager, self.config)
            self.integrity_manager.sync()
        except Exception as error:
            print(error)
            traceback.print_exc()
            raise

    def _reset_vector_collection_if_new_chat(self) -> None:
        """Reset vectors only when there are no L1 compacted memories for this chat."""
        l1_folder_exists = os.path.isdir(self.paths.l1_dir)
        if not l1_folder_exists:
            self.vector_manager.reset_collection()
            return

        l1_files = [name for name in os.listdir(self.paths.l1_dir) if name.endswith(".json")]
        if not l1_files:
            self.vector_manager.reset_collection()

    def build_chat_messages(self, user_text: str) -> list[dict]:
        """Build the single user message payload that contains the assembled memory prompt."""
        try:
            active_messages = self.conversation.read_all() or []
            prompt_text = self.prompt_builder.build_prompt(user_text, active_messages)
            return [{"role": "user", "content": prompt_text}]
        except Exception as error:
            print(error)
            traceback.print_exc()
            return [{"role": "user", "content": user_text}]

    def on_message(self, role: str, content: str, kind: str = ""):
        """Append message to L0 and queue compaction when thresholds are reached."""
        try:
            self.conversation.append(role, content, kind=kind)
            l0_items = self.conversation.read_all()
            state = self.state_store.load()
            planned_state = self.planner.plan(state, l0_count=len(l0_items))
            self.state_store.save(planned_state)
        except Exception as error:
            print(error)
            traceback.print_exc()

    def after_assistant_sent(self) -> bool:
        """Run one compaction job and keep vector index synchronized."""
        try:
            did_run_job = self.runner.run_one()
            if did_run_job:
                self.integrity_manager.sync()
            return did_run_job
        except Exception as error:
            print(error)
            traceback.print_exc()
            return False
