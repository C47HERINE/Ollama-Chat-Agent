import json
import time
import traceback
from .helpers import read_json, write_json

class ConversationBuffer:
    def __init__(self, active_path, archive_path):
        self.active_path = active_path
        self.archive_path = archive_path

    def read_all(self) -> list:
        try:
            return read_json(self.active_path) or []
        except Exception as e:
            print(e)
            traceback.print_exc()
            return []

    def append(self, role: str, content: str, kind: str = ""):
        try:
            item = {
                "role": role,
                "content": content,
                "kind": kind,
                "timestamp": time.time(),
            }
            current_data = self.read_all()
            current_data.append(item)
            write_json(self.active_path, current_data)
        except Exception as e:
            print(e)
            traceback.print_exc()

    def pop_oldest(self, count: int) -> list:
        try:
            current_data = self.read_all()
            if len(current_data) <= count:
                # To avoid race conditions, don't modify if a compaction is already planned
                return []
            
            to_pop = current_data[:count]
            remaining = current_data[count:]
            write_json(self.active_path, remaining)
            return to_pop
        except Exception as e:
            print(e)
            traceback.print_exc()
            return []

    def archive_many(self, items: list):
        try:
            if not items:
                return
            
            # Read existing archive, append new items, and write back
            archive_data = read_json(self.archive_path) or []
            archive_data.extend(items)
            write_json(self.archive_path, archive_data)

        except (IOError, TypeError) as e:
            print(e)
            traceback.print_exc()
