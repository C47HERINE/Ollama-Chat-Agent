import os
import time

import requests


class TelegramBot:
    def __init__(self, token):
        self.bot_token = token
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}/"
        self.offset = None
        self.timeout = 30

    def get_updates(self):
        try:
            method = "getUpdates"
            parameters = {"timeout": self.timeout}
            if self.offset is not None:
                parameters["offset"] = self.offset
            response = requests.get(
                self.base_url + method,
                params=parameters,
                timeout=self.timeout + 30,
            )
            response.raise_for_status()
            results = response.json().get("result") or []
            for update in results:
                update_id = update.get("update_id")
                self.offset = update_id + 1
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                if chat_id is None:
                    continue
                text = (message.get("text") or "")
                if not text:
                    continue
                user = message.get("from") or {}
                first_name = user.get("first_name", "User")
                yield chat_id, text, first_name
            time.sleep(0.3)

        except requests.exceptions.RequestException as error:
            print(f"[NET_ERROR] {error}")
            time.sleep(5)

        except Exception as error:
            print(f"[UNEXPECTED_ERROR] {error}")
            time.sleep(2)

    def send_message(self, chat_id, text):
        disable_web_page_preview = True
        method = "sendMessage"
        parameters = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        response = requests.post(self.base_url + method, params=parameters, timeout=60)
        response.raise_for_status()
        return response.json()

    def send_voice(self, chat_id, wav_path, caption=None):
        method = "sendVoice"
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"Voice file not found: {wav_path}")
        with open(wav_path, "rb") as voice_file:
            files = {"voice": voice_file}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
            request_post = requests.post(
                self.base_url + method, data=data, files=files, timeout=120
            )
        request_post.raise_for_status()
        return request_post.json()

    def send_chat_action(self, chat_id: int, action: str):
        method = "sendChatAction"
        parameters = {"chat_id": chat_id, "action": action}
        response = requests.post(self.base_url + method, params=parameters, timeout=15)
        response.raise_for_status()
        return response.json()
