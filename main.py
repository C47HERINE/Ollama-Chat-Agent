from telegram_bot import TelegramBot
from ollama_chat import OllamaChatbot
from autopilot.autopilot import AutoPilot
from dotenv import load_dotenv
import os, time, requests

load_dotenv()

def require_env(name):
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val

def main():
    telegram_bot_token = require_env("TELEGRAM_BOT_TOKEN")
    tg = TelegramBot(telegram_bot_token)
    llm = OllamaChatbot()
    autopilot = AutoPilot(tick_every_seconds=30)

    # Used by AutoPilot for autonomous messages
    def generate_fn(telegram_chat_id, prompt_text):
        llm.use_chat(telegram_chat_id)
        return llm.ask(prompt_text, stream_to_console=False)

    def send_fn(telegram_chat_id, text_to_send):
        tg.send_message(telegram_chat_id, text_to_send)
        # Track outbound so cooldowns + pending counters stay accurate.
        autopilot.observe_outbound(telegram_chat_id, text_to_send, cooldown_minutes=180)

    offset = None
    print("Main loop started...")

    while True:
        try:
            autopilot.tick(send_fn=send_fn, generate_fn=generate_fn)

            updates = tg.get_updates(offset)

            autopilot.tick(send_fn=send_fn, generate_fn=generate_fn)

            if updates.get("ok") and updates.get("result"):
                for chat_id, text, user_first, update_id in tg.extract_messages(updates):
                    offset = update_id + 1

                    print(f"Received from {user_first} (chat {chat_id}): {text}")

                    autopilot.register_chat(chat_id)

                    if text == "/start":
                        reply = f"Hi {user_first}! I'm online."
                        tg.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        continue

                    if text == "/pause":
                        st = autopilot.load_state(chat_id)
                        st["paused"] = True
                        autopilot.save_state(chat_id, st)
                        reply = "Paused. I won't initiate messages here."
                        tg.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        continue

                    if text == "/resume":
                        st = autopilot.load_state(chat_id)
                        st["paused"] = False
                        autopilot.save_state(chat_id, st)
                        reply = "Resumed. I may initiate messages again."
                        tg.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        continue

                    if text == "/reset":
                        conv_path = os.path.join(llm.state_dir, f"conversation_{chat_id}.json")
                        if os.path.exists(conv_path):
                            os.remove(conv_path)
                        llm.use_chat(chat_id)  # reload empty history

                        autopilot.reset_state(chat_id)

                        reply = "Reset memory + state for this chat."
                        tg.send_message(chat_id, reply)
                        autopilot.observe_outbound(chat_id, reply, cooldown_minutes=10)
                        continue

                    if text == "/status":
                        reply = autopilot.format_status(chat_id)
                        tg.send_message(chat_id, reply)
                        continue

                    autopilot.observe_inbound(chat_id, text)

                    llm.use_chat(chat_id)
                    reply = llm.ask(text, stream_to_console=False) or ""

                    tg.send_message(chat_id, reply)


                    autopilot.observe_outbound(chat_id, reply, cooldown_minutes=1, allow_addon=True)

        except requests.exceptions.RequestException as e:
            print(f"Network error: {e}")
            time.sleep(5)
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(2)

main()