# ollama_chat.py
import json
import os
import requests
from dotenv import load_dotenv
from core.logger import core_log
from memory_core.file_index import read_text

load_dotenv()

class OllamaChatbot:
    """Chat wrapper for Ollama."""
    def __init__(self, memory):
        self.memory = memory
        self.model = os.getenv("OLLAMA_MODEL") or ""
        self.host = (os.getenv("OLLAMA_HOST") or "").rstrip("/")

        if not self.model:
            raise RuntimeError("Missing required env: OLLAMA_MODEL")
        if not self.host:
            raise RuntimeError("Missing required env: OLLAMA_HOST")

        self._chat_id = None

        print(f"[Ollama] Host: {self.host}")
        print(f"[Ollama] Model: {self.model}")

    def use_chat(self, chat_id: int):
        self._chat_id = chat_id

    # -------------------------
    # Daily raw readers
    # -------------------------
    def _load_json_any(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return json.load(f)
        except Exception as e:
            core_log("OLLAMA_JSON_LOAD_FAIL", path=path, err=str(e))
            return None

    def _normalize_daily_data(self, data):
        """
        Normalize various historical formats into a list of dict entries
        shaped like: {role, content, time?}

        Supports:
          - NEW daily_raw format: [ {role,time,content}, ... ]
          - OLD saved format: {history:[{role,content}, ...]}
          - Also {messages:[...]} or {result:[...]} just in case
        """
        if data is None:
            return []

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ("history", "messages", "result"):
                v = data.get(key)
                if isinstance(v, list):
                    return v

        return []

    def _coerce_role(self, role_raw: str) -> str:
        r = (role_raw or "").strip().lower()
        if r in ("user", "assistant", "system"):
            return r
        if r in ("ai", "bot", "kara"):
            return "assistant"
        if r in ("human", "client"):
            return "user"
        return ""

    def _extract_content(self, entry: dict) -> str:
        for k in ("content", "text", "message"):
            v = entry.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

        for k in ("message", "msg"):
            v = entry.get(k)
            if isinstance(v, dict):
                inner = v.get("content")
                if isinstance(inner, str) and inner.strip():
                    return inner.strip()

        return ""

    def _entries_to_messages(self, entries, label: str):
        """
        Convert normalized entries to valid ollama chat messages.

        NOTE:
        - No timestamps injected into content (as requested).
        """
        out = []
        bad_roles = 0
        missing_content = 0

        for e in entries:
            if not isinstance(e, dict):
                continue

            role = self._coerce_role(e.get("role"))
            if not role:
                bad_roles += 1
                continue

            content = self._extract_content(e)
            if not content:
                missing_content += 1
                continue

            out.append({"role": role, "content": content})

        core_log(
            "OLLAMA_ENTRIES_CONVERT",
            label=label,
            in_count=len(entries) if isinstance(entries, list) else 0,
            out_count=len(out),
            bad_roles=bad_roles,
            missing_content=missing_content,
        )
        return out

    # -------------------------
    # Message builder
    # -------------------------
    def build_messages(self, user_text: str):
        chat_id = self._chat_id

        today = self.memory.today_key()
        yesterday = self.memory.yesterday_key()

        d1_path = os.path.join(self.memory.paths.daily_raw_dir, f"{yesterday}.json")
        d0_path = os.path.join(self.memory.paths.daily_raw_dir, f"{today}.json")

        d1_raw = self._load_json_any(d1_path) if os.path.exists(d1_path) else None
        d0_raw = self._load_json_any(d0_path) if os.path.exists(d0_path) else None

        d1_entries = self._normalize_daily_data(d1_raw)
        d0_entries = self._normalize_daily_data(d0_raw)

        d1_msgs = self._entries_to_messages(d1_entries, label="D1")
        d0_msgs = self._entries_to_messages(d0_entries, label="D0")

        core_log(
            "OLLAMA_HISTORY_BUILD",
            chat_id=chat_id,
            today=today,
            yesterday=yesterday,
            d1_path=d1_path,
            d1_exists=os.path.exists(d1_path),
            d1_type=type(d1_raw).__name__ if d1_raw is not None else None,
            d1_msgs=len(d1_msgs),
            d0_path=d0_path,
            d0_exists=os.path.exists(d0_path),
            d0_type=type(d0_raw).__name__ if d0_raw is not None else None,
            d0_msgs=len(d0_msgs),
        )

        # Debug if file exists but parses empty
        if os.path.exists(d1_path) and len(d1_msgs) == 0:
            try:
                raw_txt = read_text(d1_path)
                core_log("OLLAMA_D1_DEBUG", chars=len(raw_txt), head=raw_txt[:400], tail=raw_txt[-400:])
            except Exception as e:
                core_log("OLLAMA_D1_DEBUG_FAIL", err=str(e))

        # Build injection context ONCE from MemoryEngine (authoritative)
        injected_ctx = self.memory.build_context_text() or ""

        # Ordering:
        # - system injection first (lowest priority *within* ollama, but it’s one block)
        # - then D1 / D0 (more recent turns)
        # - then current user message last
        messages = []
        if injected_ctx.strip():
            messages.append({"role": "system", "content": injected_ctx})

        messages.extend(d1_msgs)
        messages.extend(d0_msgs)
        messages.append({"role": "user", "content": (user_text or "")})

        core_log(
            "OLLAMA_REQ",
            chat_id=chat_id,
            msg_count=len(messages),
            sys_count=sum(1 for m in messages if m.get("role") == "system"),
            d1_count=len(d1_msgs),
            d0_count=len(d0_msgs),
            user_chars=len(user_text or ""),
            injected_ctx_chars=len(injected_ctx),
        )

        return messages

    def stream_chat(self, messages, on_token=None):
        url = f"{self.host}/api/chat"
        payload = {"model": self.model, "messages": messages, "stream": True}

        r = requests.post(url, json=payload, stream=True, timeout=180)
        r.raise_for_status()

        full_text = ""
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = chunk.get("message") or {}
            token = msg.get("content") or ""
            if token:
                full_text += token
                if on_token:
                    on_token(token)

            if chunk.get("done") is True:
                break

        return full_text

    def ask(self, user_text: str, stream_to_console: bool = True) -> str:
        messages = self.build_messages(user_text)

        if stream_to_console:
            print("Assistant: ", end="", flush=True)
            assistant_text = self.stream_chat(messages, on_token=lambda c: print(c, end="", flush=True))
            print()
        else:
            assistant_text = self.stream_chat(messages)

        return (assistant_text or "").strip()