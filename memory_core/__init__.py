"""Public package entry points for the memory subsystem."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .introspection import IntrospectionEngine

if TYPE_CHECKING:
    from .memory_manager import MemoryManager


class MemoryCore:
    """High-level memory package facade used by `main.py`.

    This class keeps per-chat `MemoryManager` instances cached so each chat
    initializes expensive dependencies only once.
    """

    def __init__(self, root: str, config_path: str, prompts_path: str, llm, time_utils):
        self.root = root
        self.config_path = config_path
        self.prompts_path = prompts_path
        self.llm = llm
        self.introspection = IntrospectionEngine(time_utils)
        self._managers: dict[int, MemoryManager] = {}

    def get_manager(self, chat_id: int) -> MemoryManager:
        from .memory_manager import MemoryManager

        chat_id = int(chat_id)
        if chat_id not in self._managers:
            self._managers[chat_id] = MemoryManager(
                root=self.root,
                chat_id=chat_id,
                llm=self.llm,
                config_path=self.config_path,
                prompts_path=self.prompts_path,
            )
        return self._managers[chat_id]


def __getattr__(name: str):
    if name == "MemoryManager":
        from .memory_manager import MemoryManager

        return MemoryManager
    raise AttributeError(name)


__all__ = ["MemoryCore", "MemoryManager", "IntrospectionEngine"]
