import json
import os
import requests


class OllamaChatbot:
    """Chat wrapper for Ollama."""

    def __init__(self):
        self._chat_id = None
        self.model = os.getenv("OLLAMA_MODEL") or ""
        self.host = (os.getenv("OLLAMA_HOST") or "").rstrip("/")

        if not self.model:
            raise RuntimeError("Missing required env: OLLAMA_MODEL")
        if not self.host:
            raise RuntimeError("Missing required env: OLLAMA_HOST")

        print(f"[Ollama] Host: {self.host}")
        print(f"[Ollama] Model: {self.model}")

    def use_chat(self, chat_id: int):
        self._chat_id = chat_id

    # -------------------------
    # Core call
    # -------------------------
    def stream_chat(self, messages, on_token=None):
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True
            }
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

    def ask_messages(self, messages, stream_to_console: bool = True) -> str:
        """Send a fully constructed messages array."""
        if stream_to_console:
            print("Assistant: ", end="", flush=True)
            assistant_text = self.stream_chat(messages, on_token=lambda c: print(c, end="", flush=True))
            print()
        else:
            assistant_text = self.stream_chat(messages)
        return (assistant_text or "").strip()

    def summarize_ask(self, user_text: str, stream_to_console: bool = True) -> str:
        """ Custom message builder"""
        with open("./user/system/system_prompt.txt", "r") as f:
            system_prompt = f.read().strip()
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": (user_text or "")}]
        return self.ask_messages(messages, stream_to_console=stream_to_console)
