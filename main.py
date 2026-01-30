import json
import os
import threading
import time
import traceback
from dotenv import load_dotenv
from autopilot.autopilot import AutoPilot
from core.ollama_chat import OllamaChatbot
from core.telegram_bot import TelegramBot
from core.voice_router import VoiceRouter
import core.timeutils as t
from memory_core.memory_manager import MemoryManager
from memory_core.introspection import IntrospectionEngine

CHAT_REGISTRY_PATH = os.path.join("agent_state", "known_chats.json")
MEM_CONFIG_PATH = os.path.join("config", "memory_config.json")
PROMPTS_PATH = os.path.join("config", "prompts.json")

load_dotenv()
ollama_model = os.getenv("OLLAMA_MODEL")
ollama_host = os.getenv("OLLAMA_HOST")
telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
print("TELEGRAM_BOT_TOKEN =", repr(telegram_bot_token))
print(f"[Ollama] Host: {ollama_host}")
print(f"[Ollama] Model: {ollama_model}")

telegram = TelegramBot(telegram_bot_token)
autopilot = AutoPilot(tick_every_seconds=30)
ollama = OllamaChatbot(ollama_model, ollama_host)
ollama_host = os.getenv("OLLAMA_HOST")
ollama_model = os.getenv("OLLAMA_MODEL")
voice_prompt = os.getenv("VOICE_PROMPT_WAV")
voice = VoiceRouter(audio_prompt_path=voice_prompt)
introspection = IntrospectionEngine(t)

def load_known_chats():
    if not os.path.exists(CHAT_REGISTRY_PATH):
        return set()
    try:
        with open(CHAT_REGISTRY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            out = set()
            for x in data:
                s = str(x).strip()
                if s.lstrip("-").isdigit():
                    out.add(int(s))
            return out
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return set()

def save_known_chats(chat_ids):
    os.makedirs(os.path.dirname(CHAT_REGISTRY_PATH), exist_ok=True)
    with open(CHAT_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(list(chat_ids)), f, indent=2)

def remember_chat(chat_id, known):
    if chat_id not in known:
        known.add(chat_id)
        save_known_chats(known)

def main():
    print("Main loop started...")
    known_chats = load_known_chats()
    for chat_id in list(known_chats):
        autopilot.register_chat(chat_id)

    # Cache MemoryManager per telegram chat id
    memories = {}

    def get_memory_manager(_chat_id: int):
        _chat_id = int(_chat_id)
        if _chat_id not in memories:
            memories[_chat_id] = MemoryManager(
                root=".",
                chat_id=_chat_id,
                llm=ollama,
                config_path=MEM_CONFIG_PATH,
                prompts_path=PROMPTS_PATH,
            )
        return memories[_chat_id]

    def ask_with_typing(_chat_id: int, msgs):
        stop = threading.Event()

        def _loop():
            while not stop.is_set():
                try:
                    telegram.send_chat_action(_chat_id, "typing")
                except Exception:
                    pass
                stop.wait(4.5)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()
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
        kind, sent_text = voice.send(telegram, chat_id, text_to_send)
        autopilot.observe_outbound(chat_id, sent_text, cooldown_minutes=180, allow_addon=False)
        mm.after_assistant_sent()

    def introspection_fn(chat_id, state):
        # Check if introspection is needed
        if introspection.should_introspect(state, silence_ms=3600_000):
            mm = get_memory_manager(chat_id)
            prompt = introspection.build_block()
            
            # Use memory manager to build context for introspection
            # We treat this as a system/internal prompt, but we need context
            msgs = mm.build_chat_messages(prompt)
            
            # Ask LLM directly (no typing indicator for internal thought)
            out = (ollama.ask_messages(msgs, stream_to_console=False) or "").strip()
            
            if out:
                # Log to active raw conversation file
                mm.on_message("system", out, kind="introspection")
                
                # Update state to mark introspection done
                state["last_introspection_ms"] = t.now_ms()
                # Note: state is a dict reference, so modification here affects the caller's state object
                # which will be saved by autopilot.tick

    # pass function objects (NO parentheses)


    while True:
        try:
            for chat_id, text, first_name in telegram.get_updates():
                remember_chat(chat_id, known_chats)
                autopilot.register_chat(chat_id)
                memory_manager = get_memory_manager(chat_id)
                # ---- Commands (minimal) ----
                if text == "/start":
                    reply = f"Hi! I'm online."
                    telegram.send_message(chat_id, reply)
                    autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                    memory_manager.after_assistant_sent()
                    continue

                if text == "/pause":
                    st = autopilot.load_state(chat_id)
                    st["paused"] = True
                    autopilot.save_state(chat_id, st)
                    reply = "Paused. I won't initiate messages here."
                    telegram.send_message(chat_id, reply)
                    autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                    memory_manager.after_assistant_sent()
                    continue

                if text == "/resume":
                    st = autopilot.load_state(chat_id)
                    st["paused"] = False
                    autopilot.save_state(chat_id, st)
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

                # ---- Normal inbound ----
                autopilot.observe_inbound(chat_id, text)

                # 1) log inbound + build context (string returned)
                memory_manager.on_message(f"user", text, kind="inbound")

                # 2) ask model with injected context
                messages = memory_manager.build_chat_messages(text)
                reply = ask_with_typing(chat_id, messages)
                if reply:

                    # 3) log outbound assistant reply (sanitized)
                    memory_manager.on_message("assistant", reply, kind="reply")

                    # 4) send reply (sanitized)
                    kind, sent_text = voice.send(telegram, chat_id, reply)

                    # 5) autopilot observes outbound
                    autopilot.observe_outbound(
                        chat_id, sent_text, cooldown_minutes=1, allow_addon=True)

                    # 6) run one compaction after send
                    memory_manager.after_assistant_sent()

            autopilot.tick(send_fn=send_fn, generate_fn=generate_fn, introspection_fn=introspection_fn)
            time.sleep(0.3)

        except Exception as e:
            print(f"main : {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()
