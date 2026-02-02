import os
import traceback
from .compaction_planner import CompactionPlanner
from .compaction_runner import CompactionRunner
from .conversation_buffer import ConversationBuffer
from .helpers import read_json, write_json, read_text
from .paths import MemoryPaths
from .prompt_library import PromptLibrary
from .state_store import StateStore
from .summarizer import Summarizer
from .vector_manager import VectorManager
from .prompt_builder import PromptBuilder
from .integrity_manager import MemoryIntegrityManager

class MemoryManager:
    def __init__(self, root: str, chat_id: int, config_path: str, prompts_path: str, llm):
        try:
            self.paths = MemoryPaths(root=root, chat_id=chat_id)
            self.paths.ensure()
            
            self.config = read_json(config_path)
            if not isinstance(self.config, dict):
                raise RuntimeError("memory_config.json must be a JSON object")

            self.vector_manager = VectorManager(collection_name=f"chat_{chat_id}")

            if not os.path.exists(self.paths.master_path()):
                self.vector_manager.reset_collection()

            self.state_store = StateStore(self.paths.state_path())
            self.state_store.ensure_exists()

            if not os.path.exists(self.paths.l0_active_path()):
                write_json(self.paths.l0_active_path(), [])

            self.conversation = ConversationBuffer(
                self.paths.l0_active_path(), self.paths.l0_archive_path()
            )

            self.prompts = PromptLibrary(prompts_path)
            
            system_prompt_path = os.path.join(self.paths.system_dir, "system_prompt.txt")
            system_prompt = read_text(system_prompt_path) or ""
            
            self.summarizer = Summarizer(prompt_lib=self.prompts, llm=llm, system_prompt=system_prompt)

            self.planner = CompactionPlanner(
                max_level_files=int(self.config.get("levels", {}).get("max_files", 3)),
                l0_max_msgs=int(self.config.get("l0", {}).get("max_msgs")),
            )

            self.runner = CompactionRunner(
                self.paths, self.state_store, self.conversation, self.summarizer, self.vector_manager,
                l0_summary_msgs=int(self.config.get("l0", {}).get("summary_msgs"))
            )
            
            self.integrity_manager = MemoryIntegrityManager(self.paths.l1_dir, self.vector_manager)
            self.prompt_builder = PromptBuilder(self.paths, self.vector_manager, self.config)
            
            self.integrity_manager.sync()
        except Exception as e:
            print(e)
            traceback.print_exc()
            raise

    def build_chat_messages(self, user_text: str) -> list[dict]:
        try:
            l0_items = self.conversation.read_all() or []
            prompt_str = self.prompt_builder.build_prompt(user_text, l0_items)
            return [{"role": "user", "content": prompt_str}]
        except Exception as e:
            print(e)
            traceback.print_exc()
            # Return a fallback message to avoid crashing the chat
            return [{"role": "user", "content": user_text}]

    def on_message(self, role: str, content: str, kind: str = ""):
        try:
            self.conversation.append(role, content, kind=kind)
            l0_items = self.conversation.read_all()
            state = self.state_store.load()
            state = self.planner.plan(state, l0_count=len(l0_items))
            self.state_store.save(state)
        except Exception as e:
            print(e)
            traceback.print_exc()

    def after_assistant_sent(self) -> bool:
        try:
            ran = self.runner.run_one()
            if ran:
                self.integrity_manager.sync()
                return True
            return False
        except Exception as e:
            print(e)
            traceback.print_exc()
            return False
