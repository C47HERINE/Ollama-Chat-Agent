from autopilot.autopilot import AutoPilot
from core.ollama_chat import OllamaChatbot
from core.logger import core_log
from core.telegram_bot import TelegramBot
import core.timeutils as core_time
from core.voice_router import VoiceRouter
from core.weather import WeatherInjector
from memory_core.memory_engine import MemoryEngine
from dotenv import load_dotenv
import os, time, requests, json

load_dotenv()

def require_env(name):
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

def main():
    telegram_bot_token = require_env("TELEGRAM_BOT_TOKEN")
    tg = TelegramBot(telegram_bot_token)
    autopilot = AutoPilot(tick_every_seconds=30)
    weather_injector = WeatherInjector(state_dir="agent_state")
    voice = VoiceRouter(audio_out_path="./user/voice/temp/voice_memo.wav", threshold_chars=250)
    core_log("VOICE_INIT", audio_out_path=voice.audio_out_path, abs=os.path.abspath(voice.audio_out_path))

    # Memory engine (writes context/runtime_injected.md and raw logs/summaries)
    memory = MemoryEngine(root=".", timeutils=core_time, context_max_chars=12000)
    llm = OllamaChatbot(memory=memory)
    known_chats = load_known_chats()
    for cid in list(known_chats):
        autopilot.register_chat(cid)

    def generate_fn(telegram_chat_id, prompt_text):
        llm.use_chat(telegram_chat_id)
        return llm.ask(prompt_text, stream_to_console=False)

    def send_fn(telegram_chat_id, text_to_send):
        """Used by AutoPilot for autonomous sends."""
        text_to_send = (text_to_send or "").strip()
        if not text_to_send:
            return
        core_log("AUTOPILOT_SEND", chat_id=telegram_chat_id, chars=len(text_to_send))
        memory.log_assistant_output(telegram_chat_id, text_to_send, kind="autopilot")
        kind, sent_text = voice.send(tg, telegram_chat_id, text_to_send)
        core_log("OUTBOUND", chat_id=telegram_chat_id, kind=kind, chars=len(sent_text or ""))
        autopilot.observe_outbound(
            telegram_chat_id,
            sent_text,
            cooldown_minutes=180,
            allow_addon=False,
            )
    offset = None
    print("Main loop started...")

    next_weather_check = 0.0
    weather_check_every_seconds = 60

    next_memory_tick = 0.0
    memory_tick_every_seconds = 30

    core_log("BOOT", model=os.getenv("OLLAMA_MODEL"), host=os.getenv("OLLAMA_HOST"))

    core_log("BOOT_SERVICES", autopilot_tick_s=30,
             weather_every_s=weather_check_every_seconds, memory_every_s=memory_tick_every_seconds)

    while True:
        try:
            core_log("TICK_LOOP", known_chats=len(autopilot.known_chats))
            autopilot.tick(send_fn=send_fn, generate_fn=generate_fn)
            now = time.time()

            # Weather injection (and log it)
            if now >= next_weather_check:
                next_weather_check = now + weather_check_every_seconds
                core_log("WEATHER_TICK", chats=len(autopilot.known_chats))
                for chat_id in list(autopilot.known_chats):
                    try:
                        injected = weather_injector.maybe_inject(chat_id)
                    except Exception as e:
                        core_log("WEATHER_INJECT_FAIL", chat_id=chat_id, error=str(e))
                        injected = ""
                    if injected:
                        core_log("WEATHER_INJECTED", chat_id=chat_id, chars=len(injected))
                        memory.log_system_event(chat_id, injected, kind="weather_injection")
                    else:
                        core_log("WEATHER_SKIP", chat_id=chat_id)

            # Memory tick (introspection + summaries). Keep it resilient.
            if now >= next_memory_tick:
                next_memory_tick = now + memory_tick_every_seconds
                any_chat = next(iter(autopilot.known_chats), None)

                core_log("MEMORY_TICK", any_chat=any_chat, chats=len(autopilot.known_chats))
                try:
                    memory.tick(llm=llm, any_chat_id_for_llm=any_chat, known_chats=autopilot.known_chats)
                except Exception as e:
                    core_log("MEMORY_TICK_FAIL", error=str(e))

            updates = tg.get_updates(offset)
            autopilot.tick(send_fn=send_fn, generate_fn=generate_fn)
            if updates.get("ok") and updates.get("result"):
                for chat_id, text, user_first, update_id in tg.extract_messages(updates):
                    offset = update_id + 1
                    text = (text or "").strip()
                    core_log("INBOUND", chat_id=chat_id, user=user_first, chars=len(text))
                    remember_chat(chat_id, known_chats)
                    autopilot.register_chat(chat_id)

                    if text == "/start":
                        reply = f"Hi {user_first}! I'm online."
                        tg.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        memory.log_system_event(chat_id, reply, kind="command_start")
                        core_log("CMD", chat_id=chat_id, name="start")
                        continue

                    if text == "/pause":
                        st = autopilot.load_state(chat_id)
                        st["paused"] = True
                        autopilot.save_state(chat_id, st)
                        reply = "Paused. I won't initiate messages here."
                        tg.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        memory.log_system_event(chat_id, reply, kind="command_pause")
                        core_log("CMD", chat_id=chat_id, name="pause")
                        continue

                    if text == "/resume":
                        st = autopilot.load_state(chat_id)
                        st["paused"] = False
                        autopilot.save_state(chat_id, st)
                        reply = "Resumed. I may initiate messages again."
                        tg.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        memory.log_system_event(chat_id, reply, kind="command_resume")
                        core_log("CMD", chat_id=chat_id, name="resume")
                        continue

                    if text == "/status":
                        reply = autopilot.format_status(chat_id)
                        tg.send_message(chat_id, reply)
                        memory.log_assistant_output(chat_id, reply, kind="command_status")
                        core_log("CMD", chat_id=chat_id, name="status")
                        continue

                    if text == "/introspect":
                        llm.use_chat(chat_id)
                        try:
                            out = memory.introspection.run_if_needed(llm=llm, chat_id=chat_id,
                                    today_key=memory.today_key(), force=True)
                            if out:
                                reply = "Introspection captured (private)."
                            else:
                                reply = "No introspection produced."
                        except Exception as e:
                            reply = f"Introspection failed: {e}"
                        tg.send_message(chat_id, reply)
                        core_log("CMD", chat_id=chat_id, name="introspect")
                        continue

                    # Normal inbound
                    autopilot.observe_inbound(chat_id, text)
                    memory.log_user_message(chat_id, text)
                    llm.use_chat(chat_id)
                    reply = (llm.ask(text, stream_to_console=False) or "").strip()

                    if reply:
                        memory.log_assistant_output(chat_id, reply, kind="reply")
                        kind, sent_text = voice.send(tg, chat_id, reply)
                        core_log("OUTBOUND", chat_id=chat_id, kind=kind, chars=len(sent_text or ""))
                        autopilot.observe_outbound(chat_id, sent_text, cooldown_minutes=1, allow_addon=True)

        except requests.exceptions.RequestException as e:
            core_log("NET_ERROR", error=str(e))
            time.sleep(5)
        except Exception as e:
            core_log("UNEXPECTED_ERROR", error=str(e))
            time.sleep(2)

main()