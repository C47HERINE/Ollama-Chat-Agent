import os
import re
import torch
from chatterbox.tts import ChatterboxTTS


class VoiceRouter:
    """Route assistant output to Telegram as text or a single voice memo."""

    def __init__(
        self,
        audio_out_path="./user/voice/temp/voice_memo.wav",
        threshold_chars=250,
        voice_command="/voice",
        device="cuda",
        audio_prompt_path=None,
        exaggeration=None,
        cfg_weight=None,
        temperature=None,
        batch_target_chars=400,
        batch_max_chars=500,
    ):
        self.audio_out_path = audio_out_path
        self.threshold_chars = int(threshold_chars)
        self.voice_command = voice_command

        env_prompt = os.getenv("VOICE_PROMPT_WAV")
        env_exaggeration = os.getenv("VOICE_EXAGGERATION")
        env_cfg = os.getenv("VOICE_CFG_WEIGHT")
        env_temperature = os.getenv("TEMPERATURE")

        self.audio_prompt_path = (
            audio_prompt_path if audio_prompt_path is not None else (env_prompt or None)
        )

        self.exaggeration = (
            float(exaggeration)
            if exaggeration is not None
            else (float(env_exaggeration) if env_exaggeration else 0.5)
        )

        self.cfg_weight = (
            float(cfg_weight)
            if cfg_weight is not None
            else (float(env_cfg) if env_cfg else 0.5)
        )

        self.temperature = (
            float(temperature)
            if temperature is not None
            else (float(env_temperature) if temperature else 0.8)
        )
        self.batch_target_chars = int(batch_target_chars)
        self.batch_max_chars = int(batch_max_chars)

        if device:
            self.device = device
        else:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.model = None

    def ensure_model(self):
        if self.model is None:
            self.model = ChatterboxTTS.from_pretrained(device=self.device)

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

    def clean_text_for_tts(self, text: str) -> str:
        if not text:
            return ""
        t = text

        # Normalize escaped newlines and real newlines
        t = t.replace("\\n", " ")
        t = t.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")

        # Normalize quotes & punctuation (NO trailing comma)
        t = (
            t.replace("’", "'").replace("‘", "'")
            .replace("“", '"').replace("”", '"')
            .replace("–", "-").replace("—", "-")
            .replace("…", "...")
        )

        # Remove non-printable chars
        t = "".join(ch for ch in t if ch.isprintable())

        # Collapse whitespace
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def find_voice_split(self, text: str):
        if not text:
            return "", ""
        idx = text.find(self.voice_command)
        if idx == -1:
            return text, ""
        prefix = text[:idx].strip()
        voice_part = text[idx + len(self.voice_command):].strip()
        return prefix, voice_part

    def should_send_voice(self, text: str) -> bool:
        if not text:
            return False
        if self.voice_command in text:
            return True
        cleaned = self.clean_text_for_tts(self.remove_emojis(text))
        return len(cleaned) >= self.threshold_chars

    def split_into_sentence_chunks(self, text: str):
        """Split into ~500-char chunks, cutting on sentence boundaries and never exceeding batch_max_chars."""
        t = self.clean_text_for_tts(text)
        if not t:
            return []

        # Sentence-ish splits keeping the delimiter.
        # Supports ., !, ? as “sentence ends”.
        parts = re.split(r"([.!?])", t)
        sentences = []
        i = 0
        while i < len(parts):
            chunk = parts[i].strip()
            if i + 1 < len(parts) and parts[i + 1] in ".!?":
                chunk = (chunk + parts[i + 1]).strip()
                i += 2
            else:
                i += 1

            if chunk:
                sentences.append(chunk)

        chunks = []
        buf = ""

        def flush_buf():
            nonlocal buf
            if buf.strip():
                chunks.append(buf.strip())
            buf = ""

        for s in sentences:
            if not buf:
                buf = s
            else:
                candidate = (buf + " " + s).strip()

                # If adding the sentence keeps us under target, keep accumulating.
                if len(candidate) <= self.batch_target_chars:
                    buf = candidate
                else:
                    # If buf is already reasonably sized, flush it and start new with s
                    if len(buf) >= int(self.batch_target_chars * 0.6):
                        flush_buf()
                        buf = s
                    else:
                        # buf is small but candidate exceeds target; accept candidate if it stays under max
                        if len(candidate) <= self.batch_max_chars:
                            buf = candidate
                        else:
                            # candidate would exceed max: flush buf and deal with s separately
                            flush_buf()
                            buf = s

            # If buffer ever exceeds max, force flush (and if a single sentence is too big, hard-split it)
            if len(buf) > self.batch_max_chars:
                if len(buf) <= self.batch_max_chars:
                    flush_buf()
                else:
                    # Hard split long content (rare): split at spaces near max
                    tmp = buf
                    buf = ""
                    while tmp:
                        if len(tmp) <= self.batch_max_chars:
                            chunks.append(tmp.strip())
                            break
                        cut = tmp.rfind(" ", 0, self.batch_max_chars)
                        if cut == -1:
                            cut = self.batch_max_chars
                        chunks.append(tmp[:cut].strip())
                        tmp = tmp[cut:].strip()

        flush_buf()

        # Final safety: never return > max
        safe = []
        for c in chunks:
            if len(c) <= self.batch_max_chars:
                safe.append(c)
            else:
                tmp = c
                while tmp:
                    if len(tmp) <= self.batch_max_chars:
                        safe.append(tmp.strip())
                        break
                    cut = tmp.rfind(" ", 0, self.batch_max_chars)
                    if cut == -1:
                        cut = self.batch_max_chars
                    safe.append(tmp[:cut].strip())
                    tmp = tmp[cut:].strip()

        return [x for x in safe if x.strip()]

    def concat_wavs(self, wav_list):
        """Concatenate a list of torch tensors (audio) along time."""
        import torch

        if not wav_list:
            return None
        # Ensure shape is [channels, samples]
        fixed = []
        for w in wav_list:
            x = w.detach()
            if x.ndim == 1:
                x = x.unsqueeze(0)
            elif x.ndim == 2:
                pass
            else:
                x = x.reshape(1, -1)
            fixed.append(x)

        # Normalize channels count to max across chunks
        max_ch = max(x.shape[0] for x in fixed)
        normed = []
        for x in fixed:
            if x.shape[0] == max_ch:
                normed.append(x)
            else:
                # Duplicate mono to match
                if x.shape[0] == 1 and max_ch > 1:
                    normed.append(x.repeat(max_ch, 1))
                else:
                    # Fallback: pad channels with zeros
                    pad = torch.zeros((max_ch - x.shape[0], x.shape[1]), device=x.device, dtype=x.dtype)
                    normed.append(torch.cat([x, pad], dim=0))

        return torch.cat(normed, dim=1)

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

    def render_voice(self, text: str) -> str:
        self.ensure_model()

        base = text.strip() if text else ""
        if not base:
            base = "..."

        chunks = self.split_into_sentence_chunks(base)
        if not chunks:
            chunks = ["..."]

        wavs = []
        for c in chunks:
            c = c.strip()
            if not c:
                continue
            if len(c) > self.batch_max_chars:
                c = c[: self.batch_max_chars]

            wav = self.model.generate(
                c,
                audio_prompt_path=self.audio_prompt_path,
                exaggeration=self.exaggeration,
                cfg_weight=self.cfg_weight,
                temperature=self.temperature
            )
            wavs.append(wav)

        final = self.concat_wavs(wavs)
        if final is None:
            raise RuntimeError("TTS produced no audio.")

        out_path = os.path.abspath(self.audio_out_path)
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        self.save_wav(out_path, final, self.model.sr)
        return out_path

    def send(self, tg, chat_id: int, assistant_text: str):
        raw_text = assistant_text or ""

        # Split based on RAW text so /voice is detected reliably
        prefix, voice_part = self.find_voice_split(raw_text)

        if voice_part:
            if prefix.strip():
                tg.send_message(chat_id, prefix.strip())

            tts_text = self.clean_text_for_tts(self.remove_emojis(voice_part))
            audio_path = self.render_voice(tts_text)
            tg.send_voice(chat_id, audio_path)
            return "voice", raw_text

        # Otherwise: length threshold on cleaned TTS version
        tts_text = self.clean_text_for_tts(self.remove_emojis(raw_text))
        if len(tts_text) >= self.threshold_chars:
            audio_path = self.render_voice(tts_text)
            tg.send_voice(chat_id, audio_path)
            return "voice", raw_text

        # Send RAW text (no cleaning)
        tg.send_message(chat_id, raw_text)
        return "text", raw_text
