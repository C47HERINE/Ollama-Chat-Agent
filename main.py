import json
import os
import threading
import time
import traceback

from dotenv import load_dotenv

import core.timeutils as time_utils
from autopilot.autopilot import AutoPilot
from core.ollama_chat import OllamaChatbot
from core.telegram_bot import TelegramBot
from core.voice_router import VoiceRouter
from memory_core.introspection import IntrospectionEngine
from memory_core.memory_manager import MemoryManager


CHAT_REGISTRY_PATH = os.path.join("user", "known_chats.json")
MEM_CONFIG_PATH = os.path.join("config", "memory_config.json")
PROMPTS_PATH = os.path.join("config", "prompts.json")

load_dotenv()
ollama_model = os.getenv("OLLAMA_MODEL")
ollama_host = os.getenv("OLLAMA_HOST")
telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
voice_prompt = os.getenv("VOICE_PROMPT_WAV")

print(f"[Ollama] Host: {ollama_host}")
print(f"[Ollama] Model: {ollama_model}")

telegram = TelegramBot(telegram_bot_token)
autopilot = AutoPilot(tick_every_seconds=30)
ollama = OllamaChatbot(ollama_model, ollama_host)
voice = VoiceRouter(audio_prompt_path=voice_prompt)
introspection = IntrospectionEngine(time_utils)


def load_known_chats():
    if not os.path.exists(CHAT_REGISTRY_PATH):
        return set()
    try:
        with open(CHAT_REGISTRY_PATH, encoding="utf-8") as chat_registry_file:
            data = json.load(chat_registry_file)
        if isinstance(data, list):
            known_chat_ids = set()
            for chat_id in data:
                chat_id_text = str(chat_id).strip()
                if chat_id_text.lstrip("-").isdigit():
                    known_chat_ids.add(int(chat_id_text))
            return known_chat_ids
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return set()


def save_known_chats(chat_ids):
    os.makedirs(os.path.dirname(CHAT_REGISTRY_PATH), exist_ok=True)
    with open(CHAT_REGISTRY_PATH, "w", encoding="utf-8") as chat_registry_file:
        json.dump(sorted(list(chat_ids)), chat_registry_file, indent=2)


def remember_chat(chat_id, known_chat_ids):
    if chat_id not in known_chat_ids:
        known_chat_ids.add(chat_id)
        save_known_chats(known_chat_ids)


def main():
    print("Main loop started...")
    known_chats = load_known_chats()
    for chat_id in list(known_chats):
        autopilot.register_chat(chat_id)

    memory_managers_by_chat_id = {}

    def get_memory_manager(chat_id: int):
        normalized_chat_id = int(chat_id)
        if normalized_chat_id not in memory_managers_by_chat_id:
            memory_managers_by_chat_id[normalized_chat_id] = MemoryManager(
                root=".",
                chat_id=normalized_chat_id,
                llm=ollama,
                config_path=MEM_CONFIG_PATH,
                prompts_path=PROMPTS_PATH,
            )
        return memory_managers_by_chat_id[normalized_chat_id]

    def ask_with_typing(chat_id: int, messages):
        stop_typing_event = threading.Event()

        def emit_typing_indicator_loop():
            while not stop_typing_event.is_set():
                try:
                    telegram.send_chat_action(chat_id, "typing")
                except Exception as error:
                    print(error)
                stop_typing_event.wait(4.5)

        typing_thread = threading.Thread(target=emit_typing_indicator_loop, daemon=True)
        typing_thread.start()
        try:
            return (ollama.ask_messages(messages, stream_to_console=False) or "").strip()
        finally:
            stop_typing_event.set()

    def generate_fn(chat_id, prompt_text):
        memory_manager = get_memory_manager(chat_id)
        messages = memory_manager.build_chat_messages(prompt_text)
        return ask_with_typing(chat_id, messages)

    def send_fn(chat_id, text_to_send):
        memory_manager = get_memory_manager(chat_id)
        memory_manager.on_message("assistant", text_to_send, kind="autopilot")
        _delivery_kind, sent_text = voice.send(telegram, chat_id, text_to_send)
        autopilot.observe_outbound(chat_id, sent_text, cooldown_minutes=180, allow_addon=False)
        memory_manager.after_assistant_sent()

    def introspection_fn(chat_id, state):
        if introspection.should_introspect(state, silence_ms=3600_000):
            memory_manager = get_memory_manager(chat_id)
            prompt = introspection.build_block()
            messages = memory_manager.build_chat_messages(prompt)
            introspection_output = (
                ollama.ask_messages(messages, stream_to_console=False) or ""
            ).strip()
            if introspection_output:
                memory_manager.on_message("system", introspection_output, kind="introspection")
                state["last_introspection_ms"] = time_utils.now_ms()

    while True:
        try:
            for chat_id, text, _first_name in telegram.get_updates():
                remember_chat(chat_id, known_chats)
                autopilot.register_chat(chat_id)
                memory_manager = get_memory_manager(chat_id)

                if text == "/start":
                    reply = "Hi! I'm online."
                    telegram.send_message(chat_id, reply)
                    autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                    memory_manager.after_assistant_sent()
                    continue

                if text == "/pause":
                    state = autopilot.load_state(chat_id)
                    state["paused"] = True
                    autopilot.save_state(chat_id, state)
                    reply = "Paused. I won't initiate messages here."
                    telegram.send_message(chat_id, reply)
                    autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                    memory_manager.after_assistant_sent()
                    continue

                if text == "/resume":
                    state = autopilot.load_state(chat_id)
                    state["paused"] = False
                    autopilot.save_state(chat_id, state)
                    reply = "Resumed. I may initiate messages again."
                    telegram.send_message(chat_id, reply)
                    autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                    memory_manager.after_assistant_sent()
                    continue

                if text == "/status":
                    reply = autopilot.format_status(chat_id) or ""
                    telegram.send_message(chat_id, reply)
                    memory_manager.after_assistant_sent()
                    continue

                autopilot.observe_inbound(chat_id, text)
                memory_manager.on_message("user", text, kind="inbound")

                messages = memory_manager.build_chat_messages(text)
                reply = ask_with_typing(chat_id, messages)
                if reply:
                    memory_manager.on_message("assistant", reply, kind="reply")
                    _delivery_kind, sent_text = voice.send(telegram, chat_id, reply)
                    autopilot.observe_outbound(
                        chat_id,
                        sent_text,
                        cooldown_minutes=1,
                        allow_addon=True,
                    )
                    memory_manager.after_assistant_sent()

            autopilot.tick(
                send_fn=send_fn,
                generate_fn=generate_fn,
                introspection_fn=introspection_fn,
            )
            time.sleep(0.3)

        except Exception as error:
            print(f"main : {error}")
            traceback.print_exc()


main()
