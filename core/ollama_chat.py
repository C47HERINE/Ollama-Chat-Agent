import json, requests

class OllamaChatbot:
    """Chat wrapper for Ollama."""
    def __init__(self, model, host):
        self.model = model
        self.host = host

    def _make_request(self, endpoint, payload):
        url = f"{self.host}{endpoint}"
        try:
            r = requests.post(url, json=payload, stream=payload.get("stream", False), timeout=180)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            print(f"[OllamaChat] Connection error: {e}")
            return None

    def stream_chat(self, messages, on_token=None):
        """Uses the /api/chat endpoint for conversational chat."""
        payload = {"model": self.model, "messages": messages, "stream": True}
        response = self._make_request("/api/chat", payload)
        if not response:
            return ""

        full_text = ""
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                chunk = json.loads(line)
                msg = chunk.get("message") or {}
                token = msg.get("content") or ""
                if token:
                    full_text += token
                    if on_token:
                        on_token(token)
                if chunk.get("done"):
                    break
            except json.JSONDecodeError:
                continue
        return full_text

    def ask_messages(self, messages, stream_to_console: bool = True) -> str:
        """Helper to stream chat messages to console or return as string."""
        if stream_to_console:
            print("Assistant: ", end="", flush=True)
            return self.stream_chat(messages, on_token=lambda c: print(c, end="", flush=True))
        else:
            return self.stream_chat(messages)