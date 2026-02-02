import os, re, wave, torch
import threading
import numpy as np
# from chatterbox.tts import ChatterboxTTS

class VoiceRouter:
    """Route assistant output to Telegram as text or a single voice memo."""
    def __init__(self, audio_prompt_path):
        self.audio_prompt_path = audio_prompt_path
        self.audio_out_path = "./user/voice/temp/voice_memo.wav"
        self.voice_command = "/voice"
        self.cfg_weight = 0.5
        self.exaggeration = 0.5
        self.temperature = 0.8
        self.threshold_chars = 250
        self.batch_target_chars = 300
        self.batch_max_chars = 600
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        # self.model = ChatterboxTTS.from_pretrained(device=self.device)
        self.model = None
        self.telegram_char_limit = 4096

    def remove_emojis(self, text: str) -> str:
        if not text:
            return ""
        emoji_pattern = re.compile(
            "["
            "\U0001f600-\U0001f64f"
            "\U0001f300-\U0001f5ff"
            "\U0001f680-\U0001f6ff"
            "\U0001f700-\U0001f77f"
            "\U0001f780-\U0001f7ff"
            "\U0001f800-\U0001f8ff"
            "\U0001f900-\U0001f9ff"
            "\U0001fa00-\U0001fa6f"
            "\U0001fa70-\U0001faff"
            "\U00002702-\U000027b0"
            "\U000024c2-\U0001f251"
            "]+",
            flags=re.UNICODE,
        )
        return emoji_pattern.sub("", text)

    def clean_text_for_tts(self, text: str) -> str:
        if not text:
            return ""
        t = text

        # --- Normalize newlines ---
        t = t.replace("\\n", " ")
        t = t.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")

        # --- Remove Markdown emphasis that causes repetition ---
        # *word* / **word** / _word_
        t = re.sub(r"[*_]{1,2}([^*_]+)[*_]{1,2}", r"\1", t)

        # --- Normalize problematic punctuation ---
        # Ellipsis & spaced dots → short pause
        t = t.replace("…", ",")
        t = re.sub(r"\.\s+\.\s+\.", ",", t)  # . . .
        t = re.sub(r"\.{3,}", ",", t)  # ..., ...., etc.

        # Normalize smart punctuation
        t = (
            t.replace("’", "'")
            .replace("‘", "'")
            .replace("“", '"')
            .replace("”", '"')
            .replace("–", "-")
            .replace("—", "-")
        )

        # --- Remove non-printable characters ---
        t = "".join(ch for ch in t if ch.isprintable())

        # --- Collapse whitespace ---
        t = re.sub(r"\s+", " ", t)

        return t

    def find_voice_split(self, text: str):
        if not text:
            return "", ""
        idx = text.find(self.voice_command)
        if idx == -1:
            return text, ""
        prefix = text[:idx]
        voice_part = text[idx + len(self.voice_command) :]
        return prefix, voice_part

    def split_into_sentence_chunks(self, text: str):
        def hard_split(s: str):
            s = s
            out = []
            while s:
                if len(s) <= max_len:
                    out.append(s)
                    break
                cut = s.rfind(" ", 0, max_len)
                if cut == -1:
                    cut = max_len
                out.append(s[:cut])
                s = s[cut:]
            return out

        tts_text = self.clean_text_for_tts(text)
        if not tts_text:
            return []
        target = self.batch_target_chars
        max_len = self.batch_max_chars

        # Split into sentences on . ! ? (keeps punctuation)
        parts = re.split(r"([.!?])", tts_text)
        sentences = []
        i = 0
        while i < len(parts):
            split_sentence = (parts[i] or "")
            if i + 1 < len(parts) and parts[i + 1] in ".!?":
                split_sentence = (split_sentence + parts[i + 1])
                i += 2
            else:
                i += 1
            if split_sentence:
                sentences.append(split_sentence)
        if not sentences:
            sentences = [tts_text]
        chunks = []
        buf = ""

        for split_sentence in sentences:
            # If one sentence is too long, flush and split it
            if len(split_sentence) > max_len:
                if buf:
                    chunks.append(buf)
                    buf = ""
                chunks.extend(hard_split(split_sentence))
                continue
            if not buf:
                buf = split_sentence
                continue
            candidate = (buf + " " + split_sentence)

            # If we can still fit under max, and we're under target, keep accumulating
            if len(candidate) <= max_len and len(buf) < target:
                buf = candidate
            else:
                chunks.append(buf)
                buf = split_sentence

        if buf:
            chunks.append(buf)
        return [c for c in chunks if c]

    def concat_wavs(self, wav_list):
        """Concatenate a list of torch tensors (audio)."""
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
                    pad = torch.zeros(
                        (max_ch - x.shape[0], x.shape[1]), device=x.device, dtype=x.dtype
                    )
                    normed.append(torch.cat([x, pad], dim=0))

        return torch.cat(normed, dim=1)

    def save_wav(self, path, wav, sample_rate):
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

    def render_voice(self, text: str):
        if self.model is None:
            from chatterbox.tts import ChatterboxTTS
            self.model = ChatterboxTTS.from_pretrained(device=self.device)

        base = self.clean_text_for_tts(text)
        if not base:
            base = "..."
        chunks = self.split_into_sentence_chunks(base)
        if not chunks:
            chunks = ["..."]
        wavs = []
        for c in chunks:
            c = c
            if not c:
                continue
            if len(c) > self.batch_max_chars:
                c = c[: self.batch_max_chars]

            wav = self.model.generate(
                c,
                audio_prompt_path=self.audio_prompt_path,
                exaggeration=self.exaggeration,
                cfg_weight=self.cfg_weight,
                temperature=self.temperature,
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

        # Truncate message if it exceeds Telegram's character limit
        if len(raw_text) > self.telegram_char_limit:
            raw_text = raw_text[:self.telegram_char_limit - 3] + "..."

        prefix, voice_part = self.find_voice_split(raw_text)

        def action_loop(action: str, stop_event, interval_s: float = 4.5):
            # local helper; NOT added to TelegramBot, no duplicates
            while not stop_event.is_set():
                try:
                    tg.send_chat_action(chat_id, action)
                except Exception:
                    pass
                stop_event.wait(interval_s)

        def send_voice_with_indicators(tts_src_text: str):
            tts_src_text = (tts_src_text or "")
            if not tts_src_text:
                tts_src_text = "..."

            # recording while generating
            stop_record = threading.Event()
            t1 = threading.Thread(target=action_loop, args=("record_voice", stop_record), daemon=True)
            t1.start()
            try:
                audio_path = self.render_voice(tts_src_text)
            finally:
                stop_record.set()

            # uploading while sending
            stop_upload = threading.Event()
            t2 = threading.Thread(target=action_loop, args=("upload_voice", stop_upload), daemon=True)
            t2.start()
            try:
                tg.send_voice(chat_id, audio_path)
            finally:
                stop_upload.set()

        # /voice path
        if voice_part:
            if prefix:
                try:
                    tg.send_chat_action(chat_id, "typing")
                except Exception as e:
                    print(e)
                    pass
                tg.send_message(chat_id, prefix)

            tts_text = self.clean_text_for_tts(self.remove_emojis(voice_part))
            send_voice_with_indicators(tts_text)
            return "voice", raw_text

        # Auto voice by length
        tts_text = self.clean_text_for_tts(self.remove_emojis(raw_text))
        if len(tts_text) >= self.threshold_chars:
            send_voice_with_indicators(tts_text)
            return "voice", raw_text

        # Text path (no generation here; typing during generation is handled in main)
        tg.send_message(chat_id, raw_text)
        return "text", raw_text