import json
import time
import re
import traceback

class Summarizer:
    """Run summary/merge tasks through the LLM using prompt templates."""
    def __init__(self, prompt_lib, llm, system_prompt: str):
        self.ollama = llm
        self.prompts = prompt_lib
        self.system_prompt = system_prompt


    def _clean_llm_output(self, text: str) -> str:
        patterns = [
            r"^\s*Okay, I'm ready.*?\n",
            r"^\s*Here is the.*?\n",
            r"^\s*Sure, here.*?\n",
            r"^\s*Diary Entry:.*?\n",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
        return text.strip()


    def _extract_structured_text(self, text: str) -> dict:
        try:
            data = {}
            # Use regex to find sections. The (?s) flag allows . to match newlines.
            bio_match = re.search(r"\*\*BIO:\*\*(.*?)\*\*RELATIONSHIPS:\*\*", text, re.DOTALL)
            relationships_match = re.search(r"\*\*RELATIONSHIPS:\*\*(.*?)\*\*PSYCHOLOGICAL_PROFILE:\*\*", text, re.DOTALL)
            psychological_profile_match = re.search(r"\*\*PSYCHOLOGICAL_PROFILE:\*\*(.*?)\*\*DIARY:\*\*", text, re.DOTALL)
            diary_match = re.search(r"\*\*DIARY:\*\*(.*?)\*\*CORE_PRINCIPLES:\*\*", text, re.DOTALL)
            core_principles_match = re.search(r"\*\*CORE_PRINCIPLES:\*\*(.*)", text, re.DOTALL)

            data['bio'] = bio_match.group(1).strip() if bio_match else ""
            
            data['relationships'] = {}
            if relationships_match:
                for line in relationships_match.group(1).strip().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        data['relationships'][key.strip().lstrip('-* ')] = value.strip()

            data['psychological_profile'] = psychological_profile_match.group(1).strip() if psychological_profile_match else ""
            data['diary'] = diary_match.group(1).strip() if diary_match else ""
            
            data['core_principles'] = []
            if core_principles_match:
                for line in core_principles_match.group(1).strip().split('\n'):
                    if line.strip():
                        data['core_principles'].append(line.strip().lstrip('- '))
            
            return data
        except Exception as e:
            print(f"Failed to parse structured text from LLM: {e}")
            print(f"LLM Output (first 100 chars): {text[:100]}...")
            traceback.print_exc()
            return {}


    def l0_to_l1(self, chunk_text: str) -> dict:
        try:
            if not chunk_text or len(chunk_text.strip()) < 10:
                return {}
            l1_diary_system = self.prompts.format("l1_diary_system")
            system_prompt = f"{self.system_prompt}\n\n{l1_diary_system}"
            user_prompt = self.prompts.format("l1_diary_user", text=chunk_text)
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            diary_text = self.ollama.ask_messages(messages, stream_to_console=False)
            diary_text = self._clean_llm_output(diary_text)
            if not diary_text:
                return {}
            l1_bullets_system = self.prompts.format("l1_bullets_system")
            system_prompt = f"{self.system_prompt}\n\n{l1_bullets_system}"
            user_prompt = self.prompts.format("l1_bullets_user", diary_entry=diary_text)
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            bullets_text = self.ollama.ask_messages(messages, stream_to_console=False)
            bullets_text = self._clean_llm_output(bullets_text)
            bullets = []
            core_principles = []
            for line in bullets_text.split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    clean_line = line[1:].strip()
                    bullets.append(clean_line)
                    if "rule" in clean_line.lower() or "must" in clean_line.lower() or "principle" in clean_line.lower():
                        core_principles.append(clean_line)

            return {
                "id": f"l1_{int(time.time())}",
                "diary": diary_text,
                "bullets": sorted(list(set(bullets))),
                "core_principles": sorted(list(set(core_principles))),
                "timestamp": str(time.time())
            }
        except Exception as e:
            print(f"An unexpected error occurred in l0_to_l1: {e}")
            traceback.print_exc()
            return {}


    def update_master(self, master_data: dict, diary: str, core_principles: list[str]) -> dict:
        try:
            master_json = json.dumps(master_data, indent=4)
            new_l1_data = {"diary": diary, "core_principles": core_principles}
            new_l1_json = json.dumps(new_l1_data, indent=4)
            
            master_updater_system = self.prompts.format("master_updater_system")
            system_prompt = f"{self.system_prompt}\n\n{master_updater_system}"
            user_prompt = self.prompts.format("master_updater_user", master_json=master_json, new_l1_json=new_l1_json)
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            
            response = self.ollama.ask_messages(messages, stream_to_console=False)
            return self._extract_structured_text(response)
        except Exception as e:
            print(f"An unexpected error occurred in update_master: {e}")
            traceback.print_exc()
            return {}