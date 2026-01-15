import json
import os
import traceback

from dotenv import load_dotenv
from autopilot.autopilot import AutoPilot
from core.ollama_chat import OllamaChatbot
from core.telegram_bot import TelegramBot
from core.voice_router import VoiceRouter
from memory_core.memory_manager import MemoryManager

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
voice = VoiceRouter(voice_prompt)

if not ollama_host:
    raise RuntimeError("Missing required env: OLLAMA_HOST")
if not ollama_model:
    raise RuntimeError("Missing required env: OLLAMA_MODEL")

ollama = OllamaChatbot(ollama_model, ollama_host)
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

    def generate_fn(prompt_text):
        """
        AutoPilot uses this to generate messages.
        We inject current context, but DO NOT log the generation prompt into L0.
        """
        auto_reply = memory_manager.build_chat_messages(prompt_text)
        text_out = (ollama.ask_messages(auto_reply, stream_to_console=False) or "").strip()
        return text_out or ""

    def send_fn(telegram_chat_id, text_to_send):
        """
        AutoPilot uses this to send autonomous messages.
        We DO log the outbound assistant message into L0, then compact once after send.
        """
        text_to_send = (text_to_send or "").strip()
        if not text_to_send:
            return
        memory_manager.on_message("assistant", text_to_send, kind="autopilot")
        _kind, _sent_text = voice.send(telegram, telegram_chat_id, text_to_send)
        autopilot.observe_outbound(telegram_chat_id,
            _sent_text, cooldown_minutes=180, allow_addon=False)
        memory_manager.after_assistant_sent()

    while True:
        try:
            for chat_id, text, first_name in telegram.get_updates():
                remember_chat(chat_id, known_chats)
                autopilot.register_chat(chat_id)
                memory_manager = get_memory_manager(chat_id)
                autopilot.tick(send_fn=send_fn, generate_fn=generate_fn)
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
                memory_manager.on_message(f"{first_name}", text, kind="inbound")

                # 2) ask model with injected context
                messages = memory_manager.build_chat_messages(text)
                reply = (ollama.ask_messages(messages, stream_to_console=False) or "").strip()

                if reply:
                    # 3) log outbound assistant reply (sanitized)
                    memory_manager.on_message("assistant", reply, kind="reply")

                    # 4) send reply (sanitized)
                    kind, sent_text = voice.send(telegram, chat_id, reply)

                    # 5) autopilot observes outbound
                    autopilot.observe_outbound(
                        chat_id, sent_text, cooldown_minutes=1, allow_addon=True
                    )

                    # 6) run one compaction after send
                    memory_manager.after_assistant_sent()
        except Exception as e:
            print(f"main : {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()
