import time
from memory_core.helpers import read_json, write_json, append_jsonl

class ConversationBuffer:
    """
    Keep L0 active.json <= 30 messages and archive compacted messages to archive.jsonl.
    """
    def __init__(self, active_path: str, archive_path: str):
        self.active_path = active_path
        self.archive_path = archive_path

    def _load(self) -> list:
        data = read_json(self.active_path, default=[])
        return data if isinstance(data, list) else []

    def _save(self, items: list) -> None:
        write_json(self.active_path, items if isinstance(items, list) else [])

    def append(self, role: str, content: str, kind: str = "") -> None:
        items = self._load()
        items.append({
            "role": str(role),
            "ts_ms": int(time.time() * 1000),
            "content": (content or "").strip(),
            "kind": (kind or "").strip(),
        })
        self._save(items)

    def count(self) -> int:
        return len(self._load())

    def read_all(self) -> list:
        return self._load()

    def pop_oldest(self, n: int) -> list:
        items = self._load()
        chunk = items[:max(0, int(n))]
        remaining = items[max(0, int(n)):]
        self._save(remaining)
        return chunk

    def archive_many(self, items: list) -> None:
        for it in items or []:
            append_jsonl(self.archive_path, it)