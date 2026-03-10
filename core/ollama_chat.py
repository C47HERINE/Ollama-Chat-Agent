import json

import requests

class OllamaChatbot:
    """Chat wrapper for Ollama."""

    def __init__(self, model, host):
        self.model = model
        self.host = host

    # -------------------------
    # Core call
    # -------------------------
    def stream_chat(self, messages, on_token=None):
        url = f"{self.host}/api/chat"
        payload = {"model": self.model, "messages": messages, "stream": True}
        response = requests.post(url, json=payload, stream=True, timeout=180)
        response.raise_for_status()
        full_text = ""
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            try:
                chunk = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            message = chunk.get("message") or {}
            token = message.get("content") or ""
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
            assistant_text = self.stream_chat(
                messages, on_token=lambda token_chunk: print(token_chunk, end="", flush=True)
            )
            print()
        else:
            assistant_text = self.stream_chat(messages)
        return (assistant_text or "")

    def summarize_ask(self, user_text: str, stream_to_console: bool = True) -> str:
        """Custom message builder"""
        with open("./user/system/system_prompt.txt", encoding="utf-8") as prompt_file:
            system_prompt = prompt_file.read()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (user_text or "")},
        ]
        return self.ask_messages(messages, stream_to_console=stream_to_console)
