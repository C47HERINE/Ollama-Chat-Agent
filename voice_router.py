import os
import re
import torch
from chatterbox.tts_turbo import ChatterboxTurboTTS


class VoiceRouter:
    """Routes assistant output to text or voice memo based on rules."""

    def __init__(
        self,
        audio_out_path="voice_memo.wav",
        threshold_chars=250,
        voice_command="/voice",
        device="cuda",
        audio_prompt_path="EllenPage.mp3",
    ):
        self.audio_out_path = audio_out_path
        self.threshold_chars = int(threshold_chars)
        self.voice_command = voice_command
        self.audio_prompt_path = audio_prompt_path

        if device:
            self.device = device
        else:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.model = None

    def ensure_model(self):
        if self.model is None:
            self.model = ChatterboxTurboTTS.from_pretrained(device=self.device)

    def remove_emojis(self, text: str) -> str:
        if not text:
            return ""
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F700-\U0001F77F"
            "\U0001F780-\U0001F7FF"
            "\U0001F800-\U0001F8FF"
            "\U0001F900-\U0001F9FF"
            "\U0001FA00-\U0001FA6F"
            "\U0001FA70-\U0001FAFF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE,
        )
        return emoji_pattern.sub("", text)

    def split_on_voice_command(self, text: str):
        t = (text or "").strip()
        if not t:
            return "", ""

        pat = re.compile(rf"(?im)^\s*{re.escape(self.voice_command)}\b")
        m = pat.search(t)
        if not m:
            return t, ""

        text_part = t[: m.start()].strip()
        voice_part = t[m.end() :].strip()
        voice_part = self.remove_emojis(voice_part).strip()
        return text_part, voice_part

    def should_send_voice_by_length(self, text: str) -> bool:
        cleaned = self.remove_emojis(text or "")
        return len(cleaned.strip()) >= self.threshold_chars

    def render_voice(self, text: str) -> str:
        self.ensure_model()

        clean = self.remove_emojis(text).strip()
        if not clean:
            clean = "..."

        wav = (
            self.model.generate(clean, audio_prompt_path=self.audio_prompt_path)
            if self.audio_prompt_path
            else self.model.generate(clean)
        )

        out_dir = os.path.dirname(self.audio_out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        self.save_wav(self.audio_out_path, wav, self.model.sr)
        return self.audio_out_path

    def save_wav(self, path, wav, sample_rate):
        import wave
        import numpy as np
        import torch

        x = wav.detach().cpu()

        if x.ndim == 1:
            x = x.unsqueeze(0)
        elif x.ndim == 2:
            if x.shape[0] > x.shape[1] and x.shape[1] <= 8:
                x = x.transpose(0, 1)

        x = x.clamp(-1, 1)
        pcm = (x * 32767.0).to(torch.int16).numpy()
        pcm = np.transpose(pcm, (1, 0))

        with wave.open(path, "wb") as wf:
            wf.setnchannels(pcm.shape[1])
            wf.setsampwidth(2)
            wf.setframerate(int(sample_rate))
            wf.writeframes(pcm.tobytes())

    def send(self, tg, chat_id: int, assistant_text: str):
        text_part, voice_part = self.split_on_voice_command(assistant_text)

        if voice_part:
            if text_part:
                tg.send_message(chat_id, text_part)
            audio_path = self.render_voice(voice_part)
            tg.send_voice(chat_id, audio_path)
            return "mixed", assistant_text

        if self.should_send_voice_by_length(assistant_text):
            audio_path = self.render_voice(assistant_text)
            tg.send_voice(chat_id, audio_path)
            return "voice", assistant_text

        tg.send_message(chat_id, assistant_text)
        return "text", assistant_text