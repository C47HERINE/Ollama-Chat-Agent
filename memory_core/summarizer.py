import json
import time
import re
import traceback
import logging

logger = logging.getLogger(__name__)

class Summarizer:
    """Run summary/merge tasks through the LLM using prompt templates."""
    def __init__(self, prompt_lib, llm):
        self.ollama = llm
        self.prompts = prompt_lib

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
            relationships_match = re.search(r"\*\*RELATIONSHIPS:\*\*(.*?)\*\*USER_STATUS:\*\*", text, re.DOTALL)
            user_status_match = re.search(r"\*\*USER_STATUS:\*\*(.*?)\*\*DIARY:\*\*", text, re.DOTALL)
            diary_match = re.search(r"\*\*DIARY:\*\*(.*?)\*\*RULES_LOCKED:\*\*", text, re.DOTALL)
            rules_locked_match = re.search(r"\*\*RULES_LOCKED:\*\*(.*)", text, re.DOTALL)

            data['bio'] = bio_match.group(1).strip() if bio_match else ""
            
            data['relationships'] = {}
            if relationships_match:
                for line in relationships_match.group(1).strip().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        data['relationships'][key.strip().lstrip('- ')] = value.strip()

            data['user_status'] = {}
            if user_status_match:
                for line in user_status_match.group(1).strip().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        data['user_status'][key.strip().lstrip('- ')] = value.strip()

            data['diary'] = diary_match.group(1).strip() if diary_match else ""
            
            data['rules_locked'] = []
            if rules_locked_match:
                for line in rules_locked_match.group(1).strip().split('\n'):
                    if line.strip():
                        data['rules_locked'].append(line.strip().lstrip('- '))
            
            return data
        except Exception as e:
            logger.error(f"Failed to parse structured text from LLM: {e}")
            logger.error(f"LLM Output (first 100 chars): {text[:100]}...")
            logger.error(traceback.format_exc())
            return {}

    def l0_to_l1(self, chunk_text: str) -> dict:
        try:
            logger.info(f"Summarizing chunk of length {len(chunk_text)} chars...")
            if not chunk_text or len(chunk_text.strip()) < 10:
                logger.warning("Chunk text is empty or too short. Skipping.")
                return {}

            logger.info(f"Content Preview: {chunk_text[:500]}...")

            system_prompt = self.prompts.format("l1_diary_system")
            user_prompt = self.prompts.format("l1_diary_user", text=chunk_text)
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            
            diary_text = self.ollama.ask_messages(messages, stream_to_console=False)
            diary_text = self._clean_llm_output(diary_text)

            if not diary_text:
                logger.warning("Failed to generate diary entry.")
                return {}

            system_prompt = self.prompts.format("l1_bullets_system")
            user_prompt = self.prompts.format("l1_bullets_user", diary_entry=diary_text)
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            
            bullets_text = self.ollama.ask_messages(messages, stream_to_console=False)
            bullets_text = self._clean_llm_output(bullets_text)
            
            bullets = []
            rules_locked = []
            for line in bullets_text.split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    clean_line = line[1:].strip()
                    bullets.append(clean_line)
                    if "rule" in clean_line.lower() or "must" in clean_line.lower():
                        rules_locked.append(clean_line)

            return {
                "id": f"l1_{int(time.time())}",
                "diary": diary_text,
                "bullets": sorted(list(set(bullets))),
                "rules_locked": sorted(list(set(rules_locked))),
                "timestamp": str(time.time())
            }
        except Exception as e:
            logger.error(f"An unexpected error occurred in l0_to_l1: {e}")
            logger.error(traceback.format_exc())
            return {}

    def update_master(self, master_data: dict, diary: str, rules_locked: list[str]) -> dict:
        try:
            master_json = json.dumps(master_data, indent=4)
            new_l1_data = {"diary": diary, "rules_locked": rules_locked}
            new_l1_json = json.dumps(new_l1_data, indent=4)
            
            system_prompt = self.prompts.format("master_updater_system")
            user_prompt = self.prompts.format("master_updater_user", master_json=master_json, new_l1_json=new_l1_json)
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            
            response = self.ollama.ask_messages(messages, stream_to_console=False)
            return self._extract_structured_text(response)
        except Exception as e:
            logger.error(f"An unexpected error occurred in update_master: {e}")
            logger.error(traceback.format_exc())
            return {}
