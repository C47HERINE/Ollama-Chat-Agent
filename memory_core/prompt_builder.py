import importlib
import json
import os
import traceback

from .helpers import read_text


class _NoopWeatherInjector:
    def weather_updater(self):
        return ""


class PromptBuilder:
    def __init__(self, paths, vector_manager, config, model_encoding="cl100k_base"):
        try:
            self.paths = paths
            self.vm = vector_manager
            self.config = config
            self.encoding = None
            if importlib.util.find_spec("tiktoken") is not None:
                tiktoken = importlib.import_module("tiktoken")
                self.encoding = tiktoken.get_encoding(model_encoding)
            self.weather_injector = _NoopWeatherInjector()
            if importlib.util.find_spec("core.weather") is not None:
                try:
                    weather = importlib.import_module("core.weather")
                    self.weather_injector = weather.WeatherInjector()
                except Exception:
                    self.weather_injector = _NoopWeatherInjector()
            
            retrieval_conf = self.config.get("retrieval", {})
            self.max_context = int(retrieval_conf.get("max_context_tokens", 32000))
            self.safety_buffer = int(retrieval_conf.get("safety_buffer_tokens", 1000))
            self.recent_count = int(retrieval_conf.get("recent_l1_count", 3))
            self.archived_count = int(retrieval_conf.get("archived_l1_count", 3))
            
            self.effective_limit = self.max_context - self.safety_buffer
        except Exception as e:
            print(e)
            traceback.print_exc()
            raise

    def _count_tokens(self, text):
        try:
            if self.encoding is None:
                return len(text) // 4
            return len(self.encoding.encode(text))
        except Exception as e:
            print(e)
            traceback.print_exc()
            return len(text) // 4 # Fallback approximation

    def _load_json(self, path):
        try:
            if not os.path.exists(path):
                return {}
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(e)
            traceback.print_exc()
            return {}

    def _read_folder(self, folder: str, exclude_files: list = None) -> str:
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
                    with open(p, encoding='utf-8') as f:
                        parts.append(f.read())
            return "\n\n".join(parts)
        except OSError as e:
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

    def build_prompt(self, user_input, active_chat_history):
        try:
            # System Prompt, User Context, Master State
            system_prompt = self._read_folder(self.paths.system_dir)
            
            personal_context_path = self.paths.personal_context_path()
            personal_context = read_text(personal_context_path) or ""
            
            other_user_context = self._read_folder(self.paths.user_context_dir, exclude_files=[personal_context_path])
            
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

            # Vector Search
            relevant_ids = self.vm.search_and_vote(user_input, top_n_files=self.archived_count)
            seen_ids = set()
            archived_text = "## ARCHIVED MEMORIES\n"
            active_core_principles = []
            for rid in relevant_ids:
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
                fpath = os.path.join(self.paths.l1_dir, f"{rid}.json")
                l1 = self._load_json(fpath)
                if l1:
                    archived_text += self._flatten_l1(l1) + "\n"
                    active_core_principles.extend(l1.get("core_principles", []))

            # Recent Memory
            l1_files = sorted([f for f in os.listdir(self.paths.l1_dir) if f.endswith(".json")])
            recent_text = "## RECENT MEMORIES\n"
            for fname in l1_files[-self.recent_count:]:
                l1_id = fname[:-5]
                if l1_id in seen_ids:
                    continue
                seen_ids.add(l1_id)
                fpath = os.path.join(self.paths.l1_dir, fname)
                l1 = self._load_json(fpath)
                if l1:
                    recent_text += self._flatten_l1(l1) + "\n"
                    active_core_principles.extend(l1.get("core_principles", []))

            # Weather
            weather_text = self.weather_injector.weather_updater() or ""
            if weather_text:
                weather_text = f"## LOW PRIORITY INFO\n{weather_text}\n"

            # Core Principles
            active_core_principles.extend(l4_data.get("core_principles", []))
            persona_anchor = "## CORE PRINCIPLES\n" + "\n".join([f"- {r}" for r in sorted(list(set(active_core_principles)))])

            # Chat History
            chat_history_slice = active_chat_history[-60:]
            chat_text = "## CURRENT CONVERSATION\n" + "".join(f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}\n" for msg in chat_history_slice)

            # Assemble and Truncate
            must_have = f"{system_prompt}\n\n{user_context_block}\n\n{master_text}\n\n{persona_anchor}\n\n{chat_text}"
            must_have_tokens = self._count_tokens(must_have)
            remaining_tokens = max(0, self.effective_limit - must_have_tokens)

            optional_context = f"{archived_text}\n\n{recent_text}\n\n{weather_text}"
            optional_tokens = self._count_tokens(optional_context)
            if optional_tokens > remaining_tokens:
                ratio = (remaining_tokens / optional_tokens) if optional_tokens > 0 else 0
                truncate_at = max(0, int(len(optional_context) * ratio))
                optional_context = optional_context[:truncate_at] + "... [TRUNCATED]"
                
            return f"{system_prompt}\n\n{user_context_block}\n\n{master_text}\n\n{optional_context}\n\n{persona_anchor}\n\n{chat_text}"

        except Exception as e:
            print(e)
            traceback.print_exc()
            return f"SYSTEM: An error occurred building the prompt. User input was: {user_input}"
