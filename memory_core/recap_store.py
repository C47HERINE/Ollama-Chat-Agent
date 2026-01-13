import os

from memory_core.helpers import ensure_dir, read_text, write_text


class RecapStore:
    """
    Create/read/delete recap files for ONE level directory.
    """

    def __init__(self, level_dir: str):
        self.level_dir = level_dir
        ensure_dir(level_dir)

    def write_new(self, prefix: str, text: str) -> str:
        existing = sorted([n for n in os.listdir(self.level_dir) if n.lower().endswith(".md")])
        idx = len(existing) + 1
        path = os.path.join(self.level_dir, f"{prefix}_{idx:06d}.md")
        write_text(path, (text or "").strip())
        return path

    def read(self, path: str) -> str:
        return read_text(path).strip()

    def delete(self, path: str) -> None:
        try:
            os.remove(path)
        except Exception:
            pass
