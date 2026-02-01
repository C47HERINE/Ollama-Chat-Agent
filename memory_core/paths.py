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
        self.l4_dir = os.path.join(self.chat_root, "l4") # Kept for master record
        self.state_dir = os.path.join(self.chat_root, "state")

    def ensure(self) -> None:
        # Only ensure directories that are actively used by the new architecture
        for d in [
            self.system_dir,
            self.user_context_dir,
            self.l0_dir,
            self.l1_dir,
            self.l4_dir, # Kept for master record
            self.state_dir
        ]:
            ensure_dir(d)

    def l0_active_path(self) -> str:
        return os.path.join(self.l0_dir, "active.json")

    def l0_archive_path(self) -> str:
        return os.path.join(self.l0_dir, "archive.jsonl")

    def master_path(self) -> str:
        # Master record is now a JSON file
        return os.path.join(self.l4_dir, "master.json")

    def state_path(self) -> str:
        return os.path.join(self.state_dir, "state.json")
