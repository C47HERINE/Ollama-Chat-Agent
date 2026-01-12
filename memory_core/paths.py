import os
from memory_core.helpers import ensure_dir

class MemoryPaths:
    """
    Resolve per-chat paths and ensure folders exist.
    """
    def __init__(self, root: str, chat_id: int):
        self.root = root
        self.chat_id = int(chat_id)

        self.chat_root = os.path.join(root, "user", "chats", str(self.chat_id))
        self.user_root = os.path.join(root, "user")
        self.system_dir = os.path.join(self.user_root, "system")
        self.user_context_dir = os.path.join(self.chat_root, "context")

        self.l0_dir = os.path.join(self.chat_root, "l0")
        self.l1_dir = os.path.join(self.chat_root, "l1")
        self.l2_dir = os.path.join(self.chat_root, "l2")
        self.l3_dir = os.path.join(self.chat_root, "l3")
        self.l4_dir = os.path.join(self.chat_root, "l4")
        self.low_dir = os.path.join(self.chat_root, "low")
        self.state_dir = os.path.join(self.chat_root, "state")
        self.temp_dir = os.path.join(self.chat_root, "temp")

    def ensure(self) -> None:
        for d in [
            self.system_dir, self.user_context_dir,
            self.l0_dir, self.l1_dir, self.l2_dir, self.l3_dir, self.l4_dir,
            self.state_dir, self.temp_dir
        ]:
            ensure_dir(d)

    def weather_active_path(self) -> str:
        return os.path.join(self.low_dir, "weather.md")

    def l0_active_path(self) -> str:
        return os.path.join(self.l0_dir, "active.json")

    def l0_archive_path(self) -> str:
        return os.path.join(self.l0_dir, "archive.jsonl")

    def master_path(self) -> str:
        return os.path.join(self.l4_dir, "master.md")

    def state_path(self) -> str:
        return os.path.join(self.state_dir, "state.json")

    def cache_path(self) -> str:
        return os.path.join(self.temp_dir, "context_cache.json")

    def context_txt_path(self) -> str:
        return os.path.join(self.temp_dir, "context.txt")