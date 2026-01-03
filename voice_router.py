import os, re, torch
from chatterbox.tts import ChatterboxTTS

class VoiceRouter:
    """Routes assistant output to text or voice memo based on rules."""

    def __init__(
        self,
        audio_out_path="voice_memo.wav",
        threshold_chars=250,
        voice_command="/voice",
        device="cuda",
        audio_prompt_path=None,
        temperature=None,
        cfg_weight=None,
    ):
        self.audio_out_path = audio_out_path
        self.threshold_chars = int(threshold_chars)
        self.voice_command = voice_command
        env_prompt = os.getenv("VOICE_PROMPT_WAV")
        env_temp = os.getenv("VOICE_TEMPERATURE")
        env_cfg = os.getenv("VOICE_CFG_WEIGHT")
        self.audio_prompt_path = audio_prompt_path if audio_prompt_path is not None else (env_prompt or None)
        self.temperature = float(temperature) if temperature is not None else (float(env_temp) if env_temp else 0.8)
        self.cfg_weight = float(cfg_weight) if cfg_weight is not None else (float(env_cfg) if env_cfg else 0.5)

        if device:
            self.device = device
        else:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.model = None

    def ensure_model(self):
        if self.model is None:
            self.model = ChatterboxTTS.from_pretrained(device=self.device)

    def strip_voice_command(self, text: str) -> str:
        if not text:
            return ""
        idx = text.find(self.voice_command)
        if idx == -1:
            return text
        return (text[:idx] + text[idx + len(self.voice_command):]).strip()

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

    def should_send_voice(self, text: str) -> bool:
        if not text:
            return False
        if self.voice_command in text:
            return True
        cleaned = self.remove_emojis(text)
        return len(cleaned) >= self.threshold_chars

    def render_voice(self, text: str) -> str:
        self.ensure_model()

        clean = self.remove_emojis(text).strip()
        if not clean:
            clean = "..."

        wav = self.model.generate(
            clean,
            audio_prompt_path=self.audio_prompt_path,
            temperature=self.temperature,
            cfg_weight=self.cfg_weight,
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
        assistant_text = assistant_text or ""

        if self.should_send_voice(assistant_text):
            tts_text = self.strip_voice_command(assistant_text)
            audio_path = self.render_voice(tts_text)
            tg.send_voice(chat_id, audio_path)
            return "voice", assistant_text

        tg.send_message(chat_id, assistant_text)
        return "text", assistant_text