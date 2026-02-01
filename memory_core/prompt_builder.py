import json
import os
import tiktoken
from .helpers import read_text, write_text
from core import weather

class PromptBuilder:
    def __init__(self, paths, vector_manager, config, model_encoding="cl100k_base"):
        self.paths = paths
        self.vm = vector_manager
        self.config = config
        self.encoding = tiktoken.get_encoding(model_encoding)
        self.weather_injector = weather.WeatherInjector()
        
        # Load settings from config
        retrieval_conf = self.config.get("retrieval", {})
        self.max_context = int(retrieval_conf.get("max_context_tokens", 32000))
        self.safety_buffer = int(retrieval_conf.get("safety_buffer_tokens", 1000))
        self.recent_count = int(retrieval_conf.get("recent_l1_count", 3))
        self.archived_count = int(retrieval_conf.get("archived_l1_count", 3))
        
        self.effective_limit = self.max_context - self.safety_buffer

    def _count_tokens(self, text):
        return len(self.encoding.encode(text))

    def _load_json(self, path):
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
            
    def _read_folder(self, folder: str) -> str:
        if not os.path.isdir(folder):
            return ""
        parts = []
        for name in sorted(os.listdir(folder)):
            p = os.path.join(folder, name)
            if os.path.isfile(p) and name.lower().endswith((".md", ".txt")):
                with open(p, 'r', encoding='utf-8') as f:
                    parts.append(f.read())
        return "\n\n".join(parts)

    def _flatten_l4(self, l4_data):
        md = "## MASTER RECORD (AI's understanding of the user)\n"
        if l4_data.get("bio"): md += f"**Bio:** {l4_data['bio']}\n"
        if l4_data.get("relationships"):
            md += "**Relationships:**\n"
            for k, v in l4_data['relationships'].items(): md += f"- {k}: {v}\n"
        if l4_data.get("user_status"):
            md += "**User Status:**\n"
            for k, v in l4_data['user_status'].items(): md += f"- {k}: {v}\n"
        return md

    def _flatten_l1(self, l1_data):
        md = f"### Entry ID: {l1_data.get('id', 'unknown')}\n"
        md += f"**Timestamp:** {l1_data.get('timestamp', '')}\n"
        md += f"**Diary:** {l1_data.get('diary_entry', '')}\n"
        return md

    def build_prompt(self, user_input, active_chat_history):
        # 1. System Prompt
        system_prompt = self._read_folder(self.paths.system_dir)

        # 2. User Context (Explicitly Wrapped)
        user_context_raw = self._read_folder(self.paths.user_context_dir)
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

        # 3. Master State (L4)
        l4_data = self._load_json(self.paths.master_path())
        master_text = self._flatten_l4(l4_data)

        # 4. Archived Memory (Vector Search)
        relevant_ids = self.vm.search_and_vote(user_input, top_n_files=self.archived_count)
        archived_text = "## ARCHIVED MEMORIES\n"
        active_rules = []
        
        for rid in relevant_ids:
            fpath = os.path.join(self.paths.l1_dir, f"{rid}.json")
            if os.path.exists(fpath):
                l1 = self._load_json(fpath)
                archived_text += self._flatten_l1(l1) + "\n"
                if "rules_locked" in l1: active_rules.extend(l1["rules_locked"])

        # 5. Recent Memory
        l1_files = sorted([f for f in os.listdir(self.paths.l1_dir) if f.endswith(".json")])
        recent_files = l1_files[-self.recent_count:]
        recent_text = "## RECENT MEMORIES\n"
        
        for fname in recent_files:
            fpath = os.path.join(self.paths.l1_dir, fname)
            l1 = self._load_json(fpath)
            recent_text += self._flatten_l1(l1) + "\n"
            if "rules_locked" in l1: active_rules.extend(l1["rules_locked"])

        # 6. Low Priority Info (Weather)
        weather_text = self.weather_injector.weather_updater()
        if weather_text:
            weather_text = f"## LOW PRIORITY INFO\n{weather_text}\n"

        # 7. Persona Anchor (Rules)
        if "hard_locked_rules" in l4_data: active_rules.extend(l4_data["hard_locked_rules"])
        unique_rules = sorted(list(set(active_rules)))
        persona_anchor = "## OPERATIONAL RULES\n" + "\n".join([f"- {r}" for r in unique_rules])

        # 8. Active Chat
        chat_text = "## CURRENT CONVERSATION\n"
        if isinstance(active_chat_history, list):
            for msg in active_chat_history:
                chat_text += f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}\n"
        else:
            chat_text += str(active_chat_history)

        # Assemble and Truncate
        must_have = f"{system_prompt}\n\n{user_context_block}\n\n{master_text}\n\n{persona_anchor}\n\n{chat_text}"
        must_have_tokens = self._count_tokens(must_have)
        
        # Available tokens for optional context (memory, weather)
        remaining_tokens = self.effective_limit - must_have_tokens
        
        optional_context = f"{archived_text}\n\n{recent_text}\n\n{weather_text}"
        optional_tokens = self._count_tokens(optional_context)
        
        if optional_tokens > remaining_tokens:
            ratio = remaining_tokens / optional_tokens if optional_tokens > 0 else 0
            cut_len = int(len(optional_context) * ratio)
            optional_context = optional_context[:cut_len] + "... [TRUNCATED]"
            
        return f"{system_prompt}\n\n{user_context_block}\n\n{master_text}\n\n{optional_context}\n\n{persona_anchor}\n\n{chat_text}"
