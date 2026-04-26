import json
import traceback
import time


def read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return None
    except (IOError, json.JSONDecodeError) as e:
        print(e, traceback.print_exc())
        return None


def read_all(active_path) -> list:
    data = read_json(active_path)
    return data if isinstance(data, list) else []


def append(active_path, role: str, content: str, kind: str = ""):
    item = {
        "role": role,
        "content": content,
        "kind": kind,
        "timestamp": time.time(),
    }
    current_data = read_all(active_path)
    current_data.append(item)
    write_json(active_path, current_data)


def write_json(path, data, indent=2):
    from os import makedirs, path as os_path
    parent = os_path.dirname(path)
    if parent:
        makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=indent, ensure_ascii=False)


def read_text(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as file:
            return file.read()
    except (IOError, FileNotFoundError):
        return None


def write_text(path, text: str):
    from os import makedirs, path as os_path
    parent = os_path.dirname(path)
    if parent:
        makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)


def render_chat_as_text(chat_history: list) -> str:
    try:
        if not isinstance(chat_history, list):
            return ""
        return "\n".join(
            f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}" for msg in chat_history)
    except Exception as e:
        print(e, traceback.print_exc())
        return ""