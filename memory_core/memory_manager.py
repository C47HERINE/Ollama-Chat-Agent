import json
import os
import traceback
from .compactor import MemoryCompactor
from .helpers import read_json, read_text, read_all, append
from .paths import MemoryPaths
from .state_store import StateStore
from .summarizer import Summarizer
from .vector_manager import VectorManager
from .prompt_builder import PromptBuilder


class MemoryManager:
    def __init__(self, root: str, chat_id: int, config_path: str, llm):
        self.paths = MemoryPaths(root=root, chat_id=chat_id)

        self.paths.ensure()
        self.config = read_json(config_path)

        self.vector_manager = VectorManager(collection_name=f"chat_{chat_id}")

        if not os.path.exists(self.paths.master_path()):
            self.vector_manager.reset_collection()
        self.state_store = StateStore(self.paths.state_path())
        self.state_store.ensure_exists()
        system_prompt_path = os.path.join(self.paths.system_dir, "system_prompt.txt")
        system_prompt = read_text(system_prompt_path) or ""

        self.prompt_builder = PromptBuilder(self.paths, self.vector_manager, self.config)

        self.summarizer = Summarizer(prompt_lib=self.prompt_builder, llm=llm, system_prompt=system_prompt)

        self.compactor = MemoryCompactor(
            paths=self.paths,
            state_store=self.state_store,
            summarizer=self.summarizer,
            vector_manager=self.vector_manager,
            l0_summary_msgs=int(self.config.get("l0", {}).get("summary_msgs")),
            max_level_files=int(self.config.get("levels", {}).get("max_files", 3)),
            l0_max_msgs=int(self.config.get("l0", {}).get("max_msgs")))

        self.sync()


    def build_chat_messages(self, user_text: str) -> list[dict]:
        try:
            l0_items = read_all(self.paths.l0_active_path()) or []
            prompt_str = self.prompt_builder.build_prompt(user_text, l0_items)
            return [{"role": "user", "content": prompt_str}]
        except Exception as e:
            print(e)
            traceback.print_exc()
            return [{"role": "user", "content": user_text}]


    def on_message(self, role: str, content: str, kind: str = ""):
        append(role=role, content=content, kind=kind, active_path=self.paths.l0_active_path())
        l0_items = read_all(self.paths.l0_active_path())
        state = self.state_store.load()
        state = self.compactor.plan(state, len(l0_items))
        self.state_store.save(state)


    def sync(self):
        if not os.path.exists(self.paths.l1_dir):
            return
        files = [file for file in os.listdir(self.paths.l1_dir) if file.endswith(".json")]
        for filename in files:
            file_path = os.path.join(self.paths.l1_dir, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            source_id = data.get("id")
            bullets = data.get("bullets", [])
            if not source_id:
                continue
            existing = self.vector_manager.collection.get(where={"source_file": source_id}, limit=1)
            if not existing.get("ids"):
                self.vector_manager.add_to_index(bullets, source_id)


    def after_assistant_sent(self) -> bool:
        try:
            ran = self.compactor.compact_once()
            if ran:
                self.sync()
                return True
            return False
        except Exception as e:
            print(e)
            traceback.print_exc()
            return False