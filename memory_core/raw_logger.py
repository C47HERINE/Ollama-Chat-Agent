import json
import os
from typing import Any, Dict, List


class RawLogger:
    """
    Append-only daily JSON logger.
    File format: a JSON array of objects:
      { "role": str, "time": "YYYY-MM-DD HH:MM:SS", "content": str }
    """

    def __init__(self, daily_raw_dir: str):
        self.daily_raw_dir = daily_raw_dir
        os.makedirs(self.daily_raw_dir, exist_ok=True)

    def daily_path(self, date_key: str) -> str:
        return os.path.join(self.daily_raw_dir, f"{date_key}.json")

    def _load_list(self, path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _atomic_write(self, path: str, data: List[Dict[str, Any]]):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def append(self, date_key: str, entry: Dict[str, Any]):
        """
        Entry MUST contain:
          role, time, content
        """
        path = self.daily_path(date_key)
        lst = self._load_list(path)

        # Enforce exact schema + order
        role = (entry.get("role") or "").strip() or "system"
        t = (entry.get("time") or "").strip()
        content = entry.get("content")
        content = "" if content is None else str(content)
        lst.append({
            "role": role,
            "time": t,
            "content": content,
        })
        self._atomic_write(path, lst)