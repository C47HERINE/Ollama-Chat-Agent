import json
import os
import threading
import time
import traceback
from urllib.parse import urlparse

import core.timeutils as t
from autopilot.autopilot import AutoPilot
from core.ollama_chat import OllamaChatbot
from core.telegram_bot import TelegramBot
from core.voice_router import VoiceRouter
from core.weather import WeatherInjector
from memory_core.helpers import read_json
from memory_core.memory_manager import MemoryManager
from memory_core.vector_manager import VectorManager


CHAT_REGISTRY_PATH = os.path.join("user", "known_chats.json")
MEM_CONFIG_PATH = os.path.join("config", "memory_config.json")
PROMPTS_PATH = os.path.join("config", "prompts.json")


def load_known_chats():
    if not os.path.exists(CHAT_REGISTRY_PATH):
        return set()
    with open(CHAT_REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        out = set()
        for x in data:
            s = str(x).strip()
            if s.lstrip("-").isdigit():
                out.add(int(s))
        return out
    return set()


def save_known_chats(chat_ids):
    os.makedirs(os.path.dirname(CHAT_REGISTRY_PATH), exist_ok=True)
    with open(CHAT_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(list(chat_ids)), f, indent=2)


def remember_chat(chat_id, known):
    if chat_id not in known:
        known.add(chat_id)
        save_known_chats(known)


def is_valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_startup_config(env=None):
    env = env or os.environ
    errors = []

    telegram_bot_token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    ollama_host = (env.get("OLLAMA_HOST") or "").strip()
    ollama_model = (env.get("OLLAMA_MODEL") or "").strip()
    voice_prompt = (env.get("VOICE_PROMPT_WAV") or "").strip()

    if not telegram_bot_token:
        errors.append("Missing required environment variable: TELEGRAM_BOT_TOKEN")
    if not ollama_host:
        errors.append("Missing required environment variable: OLLAMA_HOST")
    elif not is_valid_url(ollama_host):
        errors.append("OLLAMA_HOST must be a valid http(s) URL")
    if not ollama_model:
        errors.append("Missing required environment variable: OLLAMA_MODEL")

    if not os.path.exists(MEM_CONFIG_PATH):
        errors.append(f"Missing required file: {MEM_CONFIG_PATH}")
    if not os.path.exists(PROMPTS_PATH):
        errors.append(f"Missing required file: {PROMPTS_PATH}")
    if voice_prompt and not os.path.exists(voice_prompt):
        errors.append(f"VOICE_PROMPT_WAV does not exist: {voice_prompt}")

    memory_config = read_json(MEM_CONFIG_PATH)
    if not isinstance(memory_config, dict):
        errors.append(f"Invalid JSON configuration in {MEM_CONFIG_PATH}")

    prompts = read_json(PROMPTS_PATH)
    if not isinstance(prompts, dict):
        errors.append(f"Invalid JSON configuration in {PROMPTS_PATH}")
    elif "introspection_prompt" not in prompts:
        errors.append("Missing required prompt key: introspection_prompt")

    if errors:
        raise RuntimeError("Startup validation failed:\n- " + "\n- ".join(errors))

    return {
        "telegram_bot_token": telegram_bot_token,
        "ollama_host": ollama_host.rstrip("/"),
        "ollama_model": ollama_model,
        "voice_prompt": voice_prompt or None,
    }


def create_runtime(env=None):
    config = validate_startup_config(env=env)
    runtime = {
        "telegram": TelegramBot(config["telegram_bot_token"]),
        "autopilot": AutoPilot(tick_every_seconds=30),
        "ollama": OllamaChatbot(config["ollama_model"], config["ollama_host"]),
        "voice": VoiceRouter(audio_prompt_path=config["voice_prompt"]),
    }
    return config, runtime


def run_startup_healthchecks(runtime):
    telegram = runtime["telegram"]
    ollama = runtime["ollama"]
    return {
        "telegram": telegram.healthcheck(),
        "ollama": ollama.healthcheck(),
        "vector_db": VectorManager(collection_name="startup_healthcheck").healthcheck(),
        "weather": WeatherInjector().healthcheck(),
    }


def should_introspect(state: dict) -> bool:
    if not isinstance(state, dict):
        return False
    last_introspection_ms = state.get("last_introspection_ms", 0)
    last_inbound_ms = state.get("last_inbound_ms", 0)
    if last_introspection_ms == 0 and last_inbound_ms > 0:
        return True
    return t.now_ms() - last_introspection_ms > 3600_000


class ChatAgentApp:
    def __init__(self, runtime):
        self.telegram = runtime["telegram"]
        self.autopilot = runtime["autopilot"]
        self.ollama = runtime["ollama"]
        self.voice = runtime["voice"]
        self.known_chats = load_known_chats()
        self.memories = {}

        for chat_id in list(self.known_chats):
            self.autopilot.register_chat(chat_id)

    def get_memory_manager(self, chat_id: int):
        chat_id = int(chat_id)
        if chat_id not in self.memories:
            self.memories[chat_id] = MemoryManager(root=".", chat_id=chat_id, llm=self.ollama, config_path=MEM_CONFIG_PATH)
        return self.memories[chat_id]

    def ask_with_typing(self, chat_id: int, msgs):
        stop = threading.Event()

        def _loop():
            while not stop.is_set():
                self.telegram.send_chat_action(chat_id, "typing")
                stop.wait(4.5)

        thread = threading.Thread(target=_loop, daemon=True)
        thread.start()
        try:
            return (self.ollama.ask_messages(msgs, stream_to_console=False) or "").strip()
        finally:
            stop.set()

    def generate_fn(self, chat_id, prompt_text):
        memory_manager = self.get_memory_manager(chat_id)
        msgs = memory_manager.build_chat_messages(prompt_text)
        return self.ask_with_typing(chat_id, msgs)

    def send_fn(self, chat_id, text_to_send):
        memory_manager = self.get_memory_manager(chat_id)
        memory_manager.on_message("assistant", text_to_send, kind="autopilot")
        _, sent_text = self.voice.send(self.telegram, chat_id, text_to_send)
        self.autopilot.observe_outbound(chat_id, sent_text, cooldown_minutes=180, allow_addon=False)
        memory_manager.after_assistant_sent()

    def introspection_fn(self, chat_id, state):
        if should_introspect(state):
            memory_manager = self.get_memory_manager(chat_id)
            prompts = read_json(PROMPTS_PATH) or {}
            prompt = prompts.get("introspection_prompt", "")
            if not prompt:
                return
            msgs = memory_manager.build_chat_messages(prompt)
            out = (self.ollama.ask_messages(msgs, stream_to_console=False) or "").strip()
            if out:
                memory_manager.on_message("system", out, kind="introspection")
                state["last_introspection_ms"] = t.now_ms()

    def handle_command(self, chat_id: int, text: str, memory_manager) -> bool:
        parts = text.split(" ", 1)
        command = parts[0]
        query = parts[1] if len(parts) > 1 else ""

        if command == "/search":
            if not query:
                self.telegram.send_message(chat_id, "Usage: /search <your query>")
            else:
                top_files = memory_manager.vector_manager.search_and_vote(query)
                reply = f"Search results for '{query}':\n"
                reply += "No relevant memories found." if not top_files else "\n".join([f"- {file_id}" for file_id in top_files])
                memory_manager.on_message("assistant", reply, kind="command_search")
                self.telegram.send_message(chat_id, reply)
                self.autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10, allow_addon=False)
                memory_manager.after_assistant_sent()
            return True

        if command == "/start":
            reply = "Hi! I'm online."
            memory_manager.on_message("assistant", reply, kind="command_start")
            self.telegram.send_message(chat_id, reply)
            self.autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
            memory_manager.after_assistant_sent()
            return True

        if command == "/pause":
            state = self.autopilot.load_state(chat_id)
            state["paused"] = True
            self.autopilot.save_state(chat_id, state)
            reply = "Paused. I won't initiate messages here."
            memory_manager.on_message("assistant", reply, kind="command_pause")
            self.telegram.send_message(chat_id, reply)
            self.autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
            memory_manager.after_assistant_sent()
            return True

        if command == "/resume":
            state = self.autopilot.load_state(chat_id)
            state["paused"] = False
            self.autopilot.save_state(chat_id, state)
            reply = "Resumed. I may initiate messages again."
            memory_manager.on_message("assistant", reply, kind="command_resume")
            self.telegram.send_message(chat_id, reply)
            self.autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
            memory_manager.after_assistant_sent()
            return True

        if command == "/status":
            reply = self.autopilot.format_status(chat_id) or ""
            memory_manager.on_message("assistant", reply, kind="command_status")
            self.telegram.send_message(chat_id, reply)
            self.autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10, allow_addon=False)
            memory_manager.after_assistant_sent()
            return True

        return False

    def handle_incoming_message(self, chat_id: int, text: str):
        remember_chat(chat_id, self.known_chats)
        self.autopilot.register_chat(chat_id)
        memory_manager = self.get_memory_manager(chat_id)

        if text.startswith("/") and self.handle_command(chat_id, text, memory_manager):
            return

        self.autopilot.observe_inbound(chat_id, text)
        memory_manager.on_message("user", text, kind="inbound")
        messages = memory_manager.build_chat_messages(text)
        reply = self.ask_with_typing(chat_id, messages)
        if reply:
            memory_manager.on_message("assistant", reply, kind="reply")
            _, sent_text = self.voice.send(self.telegram, chat_id, reply)
            self.autopilot.observe_outbound(chat_id, sent_text, cooldown_minutes=1, allow_addon=True)
            memory_manager.after_assistant_sent()

    def run(self):
        while True:
            try:
                for chat_id, text, _first_name in self.telegram.get_updates():
                    self.handle_incoming_message(chat_id, text)

                self.autopilot.tick(
                    send_fn=self.send_fn,
                    generate_fn=self.generate_fn,
                    introspection_fn=self.introspection_fn,
                )
                time.sleep(0.3)
            except Exception as error:
                print(error)
                traceback.print_exc()
