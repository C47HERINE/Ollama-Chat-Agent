import json
import os
import threading
import time
import traceback
import logging
from dotenv import load_dotenv
from autopilot.autopilot import AutoPilot
from core.ollama_chat import OllamaChatbot
from core.telegram_bot import TelegramBot
from core.voice_router import VoiceRouter
import core.timeutils as t
from memory_core.memory_manager import MemoryManager
from memory_core.introspection import IntrospectionEngine

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

CHAT_REGISTRY_PATH = os.path.join("user", "known_chats.json")
MEM_CONFIG_PATH = os.path.join("config", "memory_config.json")
PROMPTS_PATH = os.path.join("config", "prompts.json")

load_dotenv()
ollama_model = os.getenv("OLLAMA_MODEL")
ollama_host = os.getenv("OLLAMA_HOST")
telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
logging.info(f"[Ollama] Host: {ollama_host}")
logging.info(f"[Ollama] Model: {ollama_model}")

telegram = TelegramBot(telegram_bot_token)
autopilot = AutoPilot(tick_every_seconds=30)
ollama = OllamaChatbot(ollama_model, ollama_host)
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
    except (OSError, ValueError, json.JSONDecodeError) as e:
        logging.warning(f"Could not load known chats: {e}")
    return set()

def save_known_chats(chat_ids):
    try:
        os.makedirs(os.path.dirname(CHAT_REGISTRY_PATH), exist_ok=True)
        with open(CHAT_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(list(chat_ids)), f, indent=2)
    except IOError as e:
        logging.error(f"Could not save known chats: {e}")

def remember_chat(chat_id, known):
    if chat_id not in known:
        known.add(chat_id)
        save_known_chats(known)

def save_debug_log(chat_id, prompt_msgs):
    debug_dir = os.path.join("user", "chats", str(chat_id), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    filename = f"prompt_log_{int(time.time())}.json"
    path = os.path.join(debug_dir, filename)
    
    data = {
        "timestamp": t.now_ms(),
        "prompt_messages": prompt_msgs
    }
    
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.info(f"[Debug] Saved prompt log to {path}")
    except Exception as e:
        logging.error(f"[Debug] Failed to save log: {e}")

def main():
    logging.info("Main loop started...")
    known_chats = load_known_chats()
    for chat_id in list(known_chats):
        autopilot.register_chat(chat_id)

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
                except Exception as e:
                    logging.warning(f"Failed to send typing action: {e}")
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
        
        st = autopilot.load_state(chat_id)
        if st.get("debug_mode", False):
            save_debug_log(chat_id, msgs)
            
        return ask_with_typing(chat_id, msgs)

    def send_fn(chat_id, text_to_send):
        mm = get_memory_manager(chat_id)
        mm.on_message("assistant", text_to_send, kind="autopilot")
        kind, sent_text = voice.send(telegram, chat_id, text_to_send)
        autopilot.observe_outbound(chat_id, sent_text, cooldown_minutes=180, allow_addon=False)
        mm.after_assistant_sent()

    def introspection_fn(chat_id, state):
        if introspection.should_introspect(state, silence_ms=3600_000):
            mm = get_memory_manager(chat_id)
            prompt = introspection.build_block()
            msgs = mm.build_chat_messages(prompt)
            out = (ollama.ask_messages(msgs, stream_to_console=False) or "").strip()
            if out:
                mm.on_message("system", out, kind="introspection")
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
                            telegram.send_message(chat_id, reply)
                        continue

                    if command == "/start":
                        reply = f"Hi! I'm online."
                        telegram.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        memory_manager.after_assistant_sent()
                        continue

                    if command == "/pause":
                        st = autopilot.load_state(chat_id)
                        st["paused"] = True
                        autopilot.save_state(chat_id, st)
                        reply = "Paused. I won't initiate messages here."
                        telegram.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        memory_manager.after_assistant_sent()
                        continue

                    if command == "/resume":
                        st = autopilot.load_state(chat_id)
                        st["paused"] = False
                        autopilot.save_state(chat_id, st)
                        reply = "Resumed. I may initiate messages again."
                        telegram.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        memory_manager.after_assistant_sent()
                        continue

                    if command == "/status":
                        reply = autopilot.format_status(chat_id) or ""
                        telegram.send_message(chat_id, reply)
                        memory_manager.after_assistant_sent()
                        continue
                        
                    if command == "/debug":
                        st = autopilot.load_state(chat_id)
                        new_mode = not st.get("debug_mode", False)
                        st["debug_mode"] = new_mode
                        autopilot.save_state(chat_id, st)
                        reply = f"Debug mode: {'ON' if new_mode else 'OFF'}"
                        telegram.send_message(chat_id, reply)
                        continue

                autopilot.observe_inbound(chat_id, text)
                memory_manager.on_message(f"user", text, kind="inbound")
                messages = memory_manager.build_chat_messages(text)
                
                st = autopilot.load_state(chat_id)
                if st.get("debug_mode", False):
                    save_debug_log(chat_id, messages)

                reply = ask_with_typing(chat_id, messages)
                if reply:
                    memory_manager.on_message("assistant", reply, kind="reply")
                    kind, sent_text = voice.send(telegram, chat_id, reply)
                    autopilot.observe_outbound(
                        chat_id, sent_text, cooldown_minutes=1, allow_addon=True)
                    memory_manager.after_assistant_sent()

            autopilot.tick(send_fn=send_fn, generate_fn=generate_fn, introspection_fn=introspection_fn)
            time.sleep(0.3)

        except Exception as e:
            logging.critical(f"FATAL ERROR in main loop: {e}")
            traceback.print_exc()

main()
