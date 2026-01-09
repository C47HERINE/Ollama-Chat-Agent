from autopilot.autopilot import AutoPilot
from core.ollama_chat import OllamaChatbot
from core.telegram_bot import TelegramBot
from core.voice_router import VoiceRouter
from memory_core.memory_manager import MemoryManager
from dotenv import load_dotenv
import os, time, requests, json

load_dotenv()

def require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val

CHAT_REGISTRY_PATH = os.path.join("agent_state", "known_chats.json")

def load_known_chats():
    if not os.path.exists(CHAT_REGISTRY_PATH):
        return set()
    try:
        with open(CHAT_REGISTRY_PATH, "r", encoding="utf-8") as f:
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

MEM_CONFIG_PATH = os.path.join("config", "memory_config.json")
PROMPTS_PATH = os.path.join("config", "prompts.json")

def main():
    telegram_bot_token = require_env("TELEGRAM_BOT_TOKEN")
    tg = TelegramBot(telegram_bot_token)

    autopilot = AutoPilot(tick_every_seconds=30)
    voice = VoiceRouter(audio_out_path="./user/voice/temp/voice_memo.wav", threshold_chars=250)

    llm = OllamaChatbot()

    known_chats = load_known_chats()
    for cid in list(known_chats):
        autopilot.register_chat(cid)

    # Cache MemoryManager per telegram chat id
    memories = {}

    def get_mem(chat_id: int) -> MemoryManager:
        chat_id = int(chat_id)
        if chat_id not in memories:
            memories[chat_id] = MemoryManager(
                root=".",
                chat_id=chat_id,
                llm=llm,
                config_path=MEM_CONFIG_PATH,
                prompts_path=PROMPTS_PATH,
            )
        return memories[chat_id]

    def generate_fn(telegram_chat_id, prompt_text):
        """
        AutoPilot uses this to generate messages.
        We inject current context, but DO NOT log the generation prompt into L0.
        """
        llm.use_chat(telegram_chat_id)
        mem = get_mem(telegram_chat_id)

        # Make sure cache is fresh enough for generation (no logging).
        # (Usually it's fresh already, but this is cheap and safe.)
        st = mem.state_store.load()
        mem.builder.update_levels(st)
        mem.builder.update_l0(mem.conv.read_all())
        ctx = mem.cache.render(order=mem.config["injection_order"])

        return llm.ask(prompt_text, stream_to_console=False, injected_ctx=ctx)

    def send_fn(telegram_chat_id, text_to_send):
        """
        AutoPilot uses this to send autonomous messages.
        We DO log the outbound assistant message into L0, then compact once after send.
        """
        text_to_send = (text_to_send or "").strip()
        if not text_to_send:
            return

        mem = get_mem(telegram_chat_id)

        # log assistant message (L0) and update context
        mem.on_message("assistant", text_to_send, kind="autopilot")

        # send to telegram
        kind, sent_text = voice.send(tg, telegram_chat_id, text_to_send)

        # tell autopilot we sent something
        autopilot.observe_outbound(
            telegram_chat_id,
            sent_text,
            cooldown_minutes=180,
            allow_addon=False,
        )

        # run one compaction job after send (if any)
        mem.after_assistant_sent()

    offset = None
    print("Main loop started...")

    while True:
        try:
            # AutoPilot tick (autonomous behavior)
            autopilot.tick(send_fn=send_fn, generate_fn=generate_fn)

            updates = tg.get_updates(offset)
            if updates.get("ok") and updates.get("result"):
                for chat_id, text, user_first, update_id in tg.extract_messages(updates):
                    offset = update_id + 1
                    text = (text or "").strip()

                    remember_chat(chat_id, known_chats)
                    autopilot.register_chat(chat_id)

                    mem = get_mem(chat_id)

                    # ---- Commands (minimal) ----
                    if text == "/start":
                        reply = f"Hi {user_first}! I'm online."
                        tg.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)

                        mem.on_message("assistant", reply, kind="command_start")
                        mem.after_assistant_sent()
                        continue

                    if text == "/pause":
                        st = autopilot.load_state(chat_id)
                        st["paused"] = True
                        autopilot.save_state(chat_id, st)
                        reply = "Paused. I won't initiate messages here."
                        tg.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)

                        mem.on_message("assistant", reply, kind="command_pause")
                        mem.after_assistant_sent()
                        continue

                    if text == "/resume":
                        st = autopilot.load_state(chat_id)
                        st["paused"] = False
                        autopilot.save_state(chat_id, st)
                        reply = "Resumed. I may initiate messages again."
                        tg.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)

                        mem.on_message("assistant", reply, kind="command_resume")
                        mem.after_assistant_sent()
                        continue

                    if text == "/status":
                        reply = autopilot.format_status(chat_id)
                        tg.send_message(chat_id, reply)

                        mem.on_message("assistant", reply, kind="command_status")
                        mem.after_assistant_sent()
                        continue

                    # ---- Normal inbound ----
                    autopilot.observe_inbound(chat_id, text)

                    # 1) log inbound + build context (string returned)
                    ctx = mem.on_message("user", text, kind="inbound")

                    # 2) ask model with injected context
                    llm.use_chat(chat_id)
                    reply = (llm.ask(text, stream_to_console=False, injected_ctx=ctx) or "").strip()

                    if reply:
                        # 3) log outbound assistant reply
                        mem.on_message("assistant", reply, kind="reply")

                        # 4) send reply
                        kind, sent_text = voice.send(tg, chat_id, reply)

                        # 5) autopilot observes outbound
                        autopilot.observe_outbound(chat_id, sent_text, cooldown_minutes=1, allow_addon=True)

                        # 6) run one compaction after send
                        mem.after_assistant_sent()

            # avoid hammering Telegram
            time.sleep(0.3)

        except requests.exceptions.RequestException as e:
            print(f"[NET_ERROR] {e}")
            time.sleep(5)
        except Exception as e:
            print(f"[UNEXPECTED_ERROR] {e}")
            time.sleep(2)

main()