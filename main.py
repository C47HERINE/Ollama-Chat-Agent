import json
import os
import threading
import time
import traceback
from urllib.parse import urlparse

from dotenv import load_dotenv

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


load_dotenv()


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


def _is_valid_url(value: str) -> bool:
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
    elif not _is_valid_url(ollama_host):
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

    checks = {
        "telegram": telegram.healthcheck(),
        "ollama": ollama.healthcheck(),
        "vector_db": VectorManager(collection_name="startup_healthcheck").healthcheck(),
        "weather": WeatherInjector().healthcheck(),
    }
    return checks


def should_introspect(state: dict) -> bool:
    if not isinstance(state, dict):
        return False
    last_introspection_ms = state.get("last_introspection_ms", 0)
    last_inbound_ms = state.get("last_inbound_ms", 0)
    if last_introspection_ms == 0 and last_inbound_ms > 0:
        return True
    if t.now_ms() - last_introspection_ms > 3600_000:
        return True
    return False


def main():
    _, runtime = create_runtime()
    run_startup_healthchecks(runtime)

    telegram = runtime["telegram"]
    autopilot = runtime["autopilot"]
    ollama = runtime["ollama"]
    voice = runtime["voice"]

    known_chats = load_known_chats()
    for chat_id in list(known_chats):
        autopilot.register_chat(chat_id)
    memories = {}

    def get_memory_manager(_chat_id: int):
        _chat_id = int(_chat_id)
        if _chat_id not in memories:
            memories[_chat_id] = MemoryManager(root=".", chat_id=_chat_id, llm=ollama, config_path=MEM_CONFIG_PATH)
        return memories[_chat_id]


    def ask_with_typing(_chat_id: int, msgs):
        stop = threading.Event()

        def _loop():
            while not stop.is_set():
                telegram.send_chat_action(_chat_id, "typing")
                stop.wait(4.5)

        thread = threading.Thread(target=_loop, daemon=True)
        thread.start()
        try:
            return (ollama.ask_messages(msgs, stream_to_console=False) or "").strip()
        finally:
            stop.set()


    def generate_fn(chat_id, prompt_text):
        mm = get_memory_manager(chat_id)
        msgs = mm.build_chat_messages(prompt_text)
        return ask_with_typing(chat_id, msgs)


    def send_fn(chat_id, text_to_send):
        mm = get_memory_manager(chat_id)
        mm.on_message("assistant", text_to_send, kind="autopilot")
        _, sent_text = voice.send(telegram, chat_id, text_to_send)
        autopilot.observe_outbound(chat_id, sent_text, cooldown_minutes=180, allow_addon=False)
        mm.after_assistant_sent()


    def introspection_fn(chat_id, state):
        if should_introspect(state):
            memory_manager = get_memory_manager(chat_id)
            prompts = read_json(PROMPTS_PATH) or {}
            prompt = prompts.get("introspection_prompt", "")
            if not prompt:
                return
            msgs = memory_manager.build_chat_messages(prompt)
            out = (ollama.ask_messages(msgs, stream_to_console=False) or "").strip()
            if out:
                memory_manager.on_message("system", out, kind="introspection")
                state["last_introspection_ms"] = t.now_ms()


    while True:
        try:
            for chat_id, text, first_name in telegram.get_updates():
                remember_chat(chat_id, known_chats)
                autopilot.register_chat(chat_id)
                memory_manager = get_memory_manager(chat_id)

                if text.startswith("/"):
                    parts = text.split(" ", 1)
                    command = parts[0]
                    query = parts[1] if len(parts) > 1 else ""

                    if command == "/search":
                        if not query:
                            telegram.send_message(chat_id, "Usage: /search <your query>")
                        else:
                            mm = get_memory_manager(chat_id)
                            top_files = mm.vector_manager.search_and_vote(query)
                            reply = f"Search results for '{query}':\n"
                            if not top_files:
                                reply += "No relevant memories found."
                            else:
                                reply += "\n".join([f"- {file_id}" for file_id in top_files])
                            mm.on_message("assistant", reply, kind="command_search")
                            telegram.send_message(chat_id, reply)
                            autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10, allow_addon=False)
                            mm.after_assistant_sent()
                        continue

                    if command == "/start":
                        reply = "Hi! I'm online."
                        memory_manager.on_message("assistant", reply, kind="command_start")
                        telegram.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        memory_manager.after_assistant_sent()
                        continue

                    if command == "/pause":
                        st = autopilot.load_state(chat_id)
                        st["paused"] = True
                        autopilot.save_state(chat_id, st)
                        reply = "Paused. I won't initiate messages here."
                        memory_manager.on_message("assistant", reply, kind="command_pause")
                        telegram.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        memory_manager.after_assistant_sent()
                        continue

                    if command == "/resume":
                        st = autopilot.load_state(chat_id)
                        st["paused"] = False
                        autopilot.save_state(chat_id, st)
                        reply = "Resumed. I may initiate messages again."
                        memory_manager.on_message("assistant", reply, kind="command_resume")
                        telegram.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        memory_manager.after_assistant_sent()
                        continue

                    if command == "/status":
                        reply = autopilot.format_status(chat_id) or ""
                        memory_manager.on_message("assistant", reply, kind="command_status")
                        telegram.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10, allow_addon=False)
                        memory_manager.after_assistant_sent()
                        continue

                autopilot.observe_inbound(chat_id, text)
                memory_manager.on_message("user", text, kind="inbound")
                messages = memory_manager.build_chat_messages(text)

                reply = ask_with_typing(chat_id, messages)
                if reply:
                    memory_manager.on_message("assistant", reply, kind="reply")
                    _, sent_text = voice.send(telegram, chat_id, reply)
                    autopilot.observe_outbound(chat_id, sent_text, cooldown_minutes=1, allow_addon=True)
                    memory_manager.after_assistant_sent()

            autopilot.tick(send_fn=send_fn, generate_fn=generate_fn, introspection_fn=introspection_fn)
            time.sleep(0.3)

        except Exception as e:
            print(e)
            traceback.print_exc()


if __name__ == "__main__":
    main()
