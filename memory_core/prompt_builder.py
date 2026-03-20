import json
import os
import tiktoken
import traceback
from .helpers import read_text
from core import weather


class PromptBuilder:
    def __init__(self, paths, vector_manager, config, model_encoding="cl100k_base"):
        self.paths = paths
        self.vm = vector_manager
        self.config = config
        try:
            self.encoding = tiktoken.get_encoding(model_encoding)
        except Exception as e:
            print(e)
            traceback.print_exc()
            self.encoding = None
        self.weather_injector = weather.WeatherInjector()
        retrieval_conf = self.config.get("retrieval", {})
        self.max_context = int(retrieval_conf.get("max_context_tokens", 32000))
        self.safety_buffer = int(retrieval_conf.get("safety_buffer_tokens", 1000))
        self.recent_count = int(retrieval_conf.get("recent_l1_count", 3))
        self.archived_count = int(retrieval_conf.get("archived_l1_count", 3))
        self.effective_limit = self.max_context - self.safety_buffer

    def _count_tokens(self, text):
        try:
            if self.encoding is None:
                return max(1, len(text) // 4)
            return len(self.encoding.encode(text))
        except Exception as e:
            print(e)
            traceback.print_exc()
            return max(1, len(text) // 4)

    def _load_json(self, path):
        try:
            if not os.path.exists(path):
                return {}
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            print(e)
            traceback.print_exc()
            return {}

    def _read_folder(self, folder: str, exclude_files: list | None = None) -> str:
        if exclude_files is None:
            exclude_files = []
        try:
            if not os.path.isdir(folder):
                return ""
            parts = []
            for name in sorted(os.listdir(folder)):
                p = os.path.join(folder, name)
                if p in exclude_files:
                    continue
                if os.path.isfile(p) and name.lower().endswith((".md", ".txt")):
                    with open(p, 'r', encoding='utf-8') as f:
                        parts.append(f.read())
            return "\n\n".join(parts)
        except IOError as e:
            print(e)
            traceback.print_exc()
            return ""

    def _flatten_l4(self, l4_data):
        try:
            md = "## MASTER RECORD (AI's understanding of the user)\n"
            if l4_data.get("bio"):
                md += f"**Bio:** {l4_data['bio']}\n"
            if l4_data.get("relationships"):
                md += "**Relationships:**\n"
                for k, v in l4_data.get('relationships', {}).items():
                    md += f"- {k}: {v}\n"
            if l4_data.get("psychological_profile"):
                md += f"**Psychological Profile:** {l4_data['psychological_profile']}\n"
            return md
        except Exception as e:
            print(e)
            traceback.print_exc()
            return "## MASTER RECORD (Error)\n"

    def _flatten_l1(self, l1_data):
        try:
            md = f"### Entry ID: {l1_data.get('id', 'unknown')}\n"
            md += f"**Timestamp:** {l1_data.get('timestamp', '')}\n"
            md += f"**Diary:** {l1_data.get('diary', '')}\n"
            return md
        except Exception as e:
            print(e)
            traceback.print_exc()
            return f"### Entry ID: {l1_data.get('id', 'unknown')} (Error)\n"

    def _build_fallback_prompt(self, user_input, active_chat_history):
        fallback_history = "".join(
            f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}\n"
            for msg in (active_chat_history or [])[-20:]
        )
        return f"{fallback_history}USER: {user_input}".strip()

    def build_prompt(self, user_input, active_chat_history):
        try:
            system_prompt = self._read_folder(self.paths.system_dir)

            personal_context_path = self.paths.personal_context_path()
            personal_context = read_text(personal_context_path) or ""
            other_user_context = self._read_folder(
                self.paths.user_context_dir,
                exclude_files=[personal_context_path]
            )
            user_context_raw = f"{personal_context}\n\n{other_user_context}".strip()

            user_context_block = ""
            if user_context_raw:
                user_context_block = (
                    "IMPORTANT INSTRUCTION: The following text inside <user_profile> tags contains "
                    "facts, history, and details about THE USER you are chatting with. "
                    "Do NOT confuse this with your own identity. This is knowledge YOU possess about THEM.\n\n"
                    "<user_profile>\n"
                    f"{user_context_raw}\n"
                    "</user_profile>\n"
                )

            l4_data = self._load_json(self.paths.master_path())
            master_text = self._flatten_l4(l4_data)

            # Build retrieval query from the last 5 L0 messages + current user input.
            window = (active_chat_history or [])[-5:]
            retrieval_query = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}"
                for m in window
                if m.get("content")
            )

            if retrieval_query:
                retrieval_query += f"\nuser: {user_input}"
            else:
                retrieval_query = user_input

            print("=== RETRIEVAL QUERY ===")
            print(retrieval_query)

            relevant_ids = self.vm.search_and_vote(
                retrieval_query,
                top_n_files=self.archived_count
            )

            print("=== RELEVANT IDS ===")
            print(relevant_ids)

            archived_text = "## ARCHIVED MEMORIES\n"
            active_core_principles = []

            for rid in relevant_ids:
                path = os.path.join(self.paths.l1_dir, f"{rid}.json")
                l1 = self._load_json(path)
                if l1:
                    archived_text += self._flatten_l1(l1) + "\n"
                    active_core_principles.extend(l1.get("core_principles", []))

            print("=== ARCHIVED TEXT ===")
            print(archived_text)

            l1_files = []
            if os.path.isdir(self.paths.l1_dir):
                l1_files = sorted(
                    [f for f in os.listdir(self.paths.l1_dir) if f.endswith(".json")]
                )

            recent_text = "## RECENT MEMORIES\n"
            for file in l1_files[-self.recent_count:]:
                path = os.path.join(self.paths.l1_dir, file)
                l1 = self._load_json(path)
                if l1:
                    recent_text += self._flatten_l1(l1) + "\n"
                    active_core_principles.extend(l1.get("core_principles", []))

            weather_text = self.weather_injector.weather_updater() or ""
            if weather_text:
                weather_text = f"## LOW PRIORITY INFO\n{weather_text}\n"

            active_core_principles.extend(l4_data.get("core_principles", []))
            persona_anchor = "## CORE PRINCIPLES\n" + "\n".join(
                [f"- {r}" for r in sorted(set(active_core_principles))]
            )

            chat_history_slice = (active_chat_history or [])[-60:]
            chat_text = "## CURRENT CONVERSATION\n" + "".join(
                f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}\n"
                for msg in chat_history_slice
            )

            must_have = (
                f"{system_prompt}\n\n"
                f"{user_context_block}\n\n"
                f"{master_text}\n\n"
                f"{persona_anchor}\n\n"
                f"{chat_text}"
            )

            must_have_tokens = self._count_tokens(must_have)
            remaining_tokens = self.effective_limit - must_have_tokens

            optional_context = f"{archived_text}\n\n{recent_text}\n\n{weather_text}"
            optional_tokens = self._count_tokens(optional_context)

            if 0 < remaining_tokens < optional_tokens:
                ratio = remaining_tokens / optional_tokens
                optional_context = optional_context[: int(len(optional_context) * ratio)] + "... [TRUNCATED]"
            elif remaining_tokens <= 0:
                optional_context = ""

            print("must_have_tokens:", must_have_tokens)
            print("remaining_tokens:", remaining_tokens)
            print("optional_tokens:", optional_tokens)
            print("archived_len:", len(archived_text))
            print("recent_len:", len(recent_text))
            print("final_optional_context:\n", optional_context)

            return (
                f"{system_prompt}\n\n"
                f"{user_context_block}\n\n"
                f"{master_text}\n\n"
                f"{optional_context}\n\n"
                f"{persona_anchor}\n\n"
                f"{chat_text}"
            )

        except Exception as e:
            print(e)
            traceback.print_exc()
            return self._build_fallback_prompt(user_input, active_chat_history)