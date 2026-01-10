import os
from memory_core.helpers import read_json, write_json
from memory_core.paths import MemoryPaths
from memory_core.state_store import StateStore
from memory_core.conversation_buffer import ConversationBuffer
from memory_core.prompt_library import PromptLibrary
from memory_core.summarizer import Summarizer
from memory_core.compaction_planner import CompactionPlanner
from memory_core.compaction_runner import CompactionRunner
from memory_core.context_cache import ContextCache
from memory_core.context_builder import ContextBuilder

class MemoryManager:
    """
    Orchestrate per-message memory updates (no ticking).
    - on_message(): append to L0, plan jobs, update cache, render injection text.
    - after_assistant_sent(): run one compaction job and refresh cache.
    """
    def __init__(self, root: str, chat_id: int, llm, config_path: str, prompts_path: str):
        self.paths = MemoryPaths(root=root, chat_id=chat_id)
        self.paths.ensure()

        self.config = read_json(config_path, default={})
        if not isinstance(self.config, dict):
            raise RuntimeError("memory_config.json must be a JSON object")

        sep = self.config.get("separation_line") or ("=" * 72)

        self.state_store = StateStore(self.paths.state_path())
        self.state_store.ensure_exists()

        # Ensure L0 active exists as []
        if not os.path.exists(self.paths.l0_active_path()):
            write_json(self.paths.l0_active_path(), [])

        self.conv = ConversationBuffer(self.paths.l0_active_path(), self.paths.l0_archive_path())

        self.prompts = PromptLibrary(prompts_path)
        self.summarizer = Summarizer(llm=llm, prompt_lib=self.prompts)

        self.planner = CompactionPlanner(
            max_level_files=int(self.config["levels"]["max_files"]),
            l0_max_msgs=int(self.config["l0"]["max_msgs"]),
        )

        self.cache = ContextCache(self.paths.cache_path(), self.paths.context_txt_path(), sep_line=sep)
        self.builder = ContextBuilder(self.paths, self.cache)
        self.runner = CompactionRunner(self.paths, self.state_store, self.conv, self.summarizer)

        # Static sections can be refreshed whenever you edit files; do it on init.
        self.builder.update_system_and_user_context()
        self.builder.update_low_priority("")  # placeholder for weather/introspection later

        # Initialize cache with current state (empty on first run)
        st = self.state_store.load()
        self.builder.update_levels(st)
        self.builder.update_l0(self.conv.read_all())
        self.cache.render(order=self.config["injection_order"])

    def on_message(self, role: str, content: str, kind: str = "") -> str:
        # 1) Append to L0
        self.conv.append(role, content, kind=kind)

        # 2) Update L0 section
        l0_items = self.conv.read_all()
        self.builder.update_l0(l0_items)

        # 3) Plan jobs only
        st = self.state_store.load()
        st = self.planner.plan(st, l0_count=len(l0_items))
        self.state_store.save(st)

        # 4) Update recap sections from current state
        self.builder.update_levels(st)

        # 5) Render final injection string
        return self.cache.render(order=self.config["injection_order"])

    def after_assistant_sent(self) -> bool:
        # Run exactly one compaction job (if any)
        ran = self.runner.run_one()
        if ran:
            st = self.state_store.load()
            self.builder.update_levels(st)
            self.builder.update_l0(self.conv.read_all())
            self.cache.render(order=self.config["injection_order"])
            return True
        return False