import os
import logging
import traceback

logger = logging.getLogger(__name__)

class MemoryPaths:
    def __init__(self, root: str, chat_id: int):
        try:
            self.root = root
            self.chat_id = str(chat_id)
            
            # Base directories
            self.chat_dir = os.path.join(self.root, "user", "chats", self.chat_id)
            self.system_dir = os.path.join(self.root, "user", "system")
            self.user_context_dir = os.path.join(self.chat_dir, "context") # Per-chat context
            
            # State and Master directories
            self.state_dir = os.path.join(self.chat_dir, "state")
            self.master_dir = os.path.join(self.chat_dir, "master")
            
            # Memory directories
            self.l1_dir = os.path.join(self.chat_dir, "l1")
            self.l0_dir = os.path.join(self.chat_dir, "l0")
            
        except Exception as e:
            logger.error(f"Failed to initialize MemoryPaths: {e}")
            logger.error(traceback.format_exc())
            raise

    def ensure(self):
        """Create all necessary directories."""
        try:
            dirs_to_create = [
                self.chat_dir,
                self.system_dir,
                self.user_context_dir, # Per-chat context
                self.state_dir,
                self.master_dir,
                self.l1_dir,
                self.l0_dir,
            ]
            for d in dirs_to_create:
                os.makedirs(d, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create directory structure: {e}")
            logger.error(traceback.format_exc())
            raise

    def l0_active_path(self) -> str:
        return os.path.join(self.l0_dir, "active.json")

    def l0_archive_path(self) -> str:
        return os.path.join(self.l0_dir, "archive.json")

    def state_path(self) -> str:
        return os.path.join(self.state_dir, "state.json")

    def master_path(self) -> str:
        return os.path.join(self.master_dir, "master.json")

    def personal_context_path(self) -> str:
        return os.path.join(self.user_context_dir, "4-catherine_personal_context.md")
