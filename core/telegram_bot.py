import os

import requests


class TelegramBot:
    def __init__(self, token):
        self.bot_token = token
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}/"

    def get_updates(self, offset=None, timeout=30):
        method = "getUpdates"
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        r = requests.get(self.base_url + method, params=params, timeout=timeout + 30)
        r.raise_for_status()
        return r.json()

    def send_message(self, chat_id, text, disable_web_page_preview=True):
        method = "sendMessage"
        params = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        r = requests.post(self.base_url + method, params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    def send_voice(self, chat_id, wav_path, caption=None):
        method = "sendVoice"
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"Voice file not found: {wav_path}")
        with open(wav_path, "rb") as f:
            files = {"voice": f}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
            r = requests.post(self.base_url + method, data=data, files=files, timeout=120)
        r.raise_for_status()
        return r.json()

    def extract_messages(self, updates):
        results = updates.get("result") or []
        for upd in results:
            update_id = upd.get("update_id")
            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is None:
                continue
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            user = msg.get("from") or {}
            first_name = user.get("first_name", "User")
            yield chat_id, text, first_name, update_id
