import os
import json

def ensure_dir(path: str) -> None:
    if path:
        os.makedirs(path, exist_ok=True)

def read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""

def write_text(path: str, text: str) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        f.write((text or "") + "\n")

def read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def write_json(path: str, obj) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def append_json(path: str, obj: dict) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def render_chat_as_text(items) -> str:
    """
    Convert JSON message objects to injection-safe plain text:
    role: content
    """
    lines = []
    for it in items or []:
        role = str(it.get("role", "")).strip()
        content = str(it.get("content", "")).strip()
        if role and content:
            lines.append(f"({role}) {content}")
    return "\n".join(lines).strip()