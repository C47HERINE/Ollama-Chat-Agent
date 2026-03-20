import json
import traceback


def read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return None
    except (IOError, json.JSONDecodeError) as e:
        print(e)
        traceback.print_exc()
        return None


def write_json(path: str, data, indent=2):
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=indent, ensure_ascii=False)
    except (IOError, TypeError) as e:
        print(e)
        traceback.print_exc()


def read_text(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        return None
    except IOError as e:
        print(e)
        traceback.print_exc()
        return None


def write_text(path: str, text: str):
    try:
        with open(path, "w", encoding="utf-8") as file:
            file.write(text)
    except IOError as e:
        print(e)
        traceback.print_exc()


def render_chat_as_text(chat_history: list) -> str:
    try:
        if not isinstance(chat_history, list):
            return ""
        return "\n".join(
            f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}"
            for msg in chat_history
            )
    except Exception as e:
        print(e)
        traceback.print_exc()
        return ""