import json
import logging
import traceback

logger = logging.getLogger(__name__)

def read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None # Return None if the file doesn't exist
    except (IOError, json.JSONDecodeError) as e:
        logger.error(f"Failed to read or parse JSON from {path}: {e}")
        logger.error(traceback.format_exc())
        return None # Return None on other errors

def write_json(path: str, data, indent=2):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
    except (IOError, TypeError) as e:
        logger.error(f"Failed to write JSON to {path}: {e}")
        logger.error(traceback.format_exc())

def read_text(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except IOError as e:
        logger.error(f"Failed to read text from {path}: {e}")
        logger.error(traceback.format_exc())
        return None

def write_text(path: str, text: str):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except IOError as e:
        logger.error(f"Failed to write text to {path}: {e}")
        logger.error(traceback.format_exc())

def render_chat_as_text(chat_history: list) -> str:
    try:
        if not isinstance(chat_history, list):
            return ""
        return "\n".join(
            f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}"
            for msg in chat_history
        )
    except Exception as e:
        logger.error(f"Failed to render chat history as text: {e}")
        logger.error(traceback.format_exc())
        return ""
