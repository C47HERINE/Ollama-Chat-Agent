import json, os, requests
from dotenv import load_dotenv
import core.timeutils as t

load_dotenv()

class OllamaChatbot:
    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL")
        self.host = os.getenv("OLLAMA_HOST")
        self.system_dir = "ollama_system_prompt"
        self.context_dir = "ollama_context"
        self.state_dir = "ollama_state"
        self.state_path = os.path.join(self.state_dir, "conversation.json")
        os.makedirs(self.system_dir, exist_ok=True)
        os.makedirs(self.context_dir, exist_ok=True)
        os.makedirs(self.state_dir, exist_ok=True)
        self.history = self.load_history()
        print(f"[Ollama] Host: {self.host}")
        print(f"[Ollama] Model: {self.model}")

    def use_chat(self, chat_id):
        self.state_path = os.path.join(self.state_dir, f"conversation_{chat_id}.json")
        self.history = self.load_history()

    def read_all_text_files(self, folder):
        if not os.path.isdir(folder):
            return ""
        parts = []
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if os.path.isfile(path) and name.lower().endswith((".txt", ".md", ".json")):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        parts.append(f.read().strip())
                except UnicodeDecodeError:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        parts.append(f.read().strip())
        return "\n\n".join(p for p in parts if p)

    def load_history(self):
        if not os.path.exists(self.state_path):
            return []
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            hist = data.get("history", [])
            if not isinstance(hist, list):
                return []
            cleaned = []
            for m in hist:
                if isinstance(m, dict) and "role" in m and "content" in m:
                    cleaned.append({"role": m["role"], "content": m["content"]})
            return cleaned
        except (OSError, json.JSONDecodeError):
            return []

    def save_history(self):
        payload = {
            "model": self.model,
            "host": self.host,
            "saved_ms": t.now_ms(),
            "history": self.history,
        }
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def inject_history_note(self, text, role="system"):
        """Append a single note into the saved conversation history."""
        text = (text or "").strip()
        if not text:
            return False
        self.history.append({"role": role, "content": text})
        self.save_history()
        return True

    def build_messages(self, user_text):
        messages = []
        dt = t.local_dt()
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H:%M")
        tod = t.time_of_day_label(dt.hour)
        wk = t.weekday_label()
        messages.append(
            {
                "role": "system",
                "content": f"Meta: Local date {date_str}, local time {time_str}, {tod}, {wk}.",
            }
        )
        system_text = self.read_all_text_files(self.system_dir)
        context_text = self.read_all_text_files(self.context_dir)
        if system_text:
            messages.append({"role": "system", "content": system_text})
        if context_text:
            messages.append({"role": "system", "content": f"Context:\n{context_text}"})
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_text})
        return messages

    def stream_chat(self, messages, on_token=None):
        url = f"{self.host}/api/chat"
        payload = {"model": self.model, "messages": messages, "stream": True}
        r = requests.post(url, json=payload, stream=True, timeout=120)
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

    def ask(self, user_text, stream_to_console=True):
        messages = self.build_messages(user_text)
        if stream_to_console:
            print("Assistant: ", end="", flush=True)
            assistant_text = self.stream_chat(
                messages,
                on_token=lambda c: print(c, end="", flush=True),
            )
            print()
        else:
            assistant_text = self.stream_chat(messages)
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": assistant_text})
        self.save_history()
        return assistant_text