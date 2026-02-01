import json
import time
import re

class Summarizer:
    """Run summary/merge tasks through the LLM using prompt templates."""
    def __init__(self, prompt_lib, llm):
        self.ollama = llm
        self.prompts = prompt_lib

    def _clean_llm_output(self, text: str) -> str:
        # Remove common conversational filler from the start of the response
        patterns = [
            r"^\s*Okay, I'm ready.*?\n",
            r"^\s*Okay, I'm ready!.*?\n",
            r"^\s*Here is the.*?\n",
            r"^\s*Sure, here is the.*?\n",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
        return text.strip()

    def l0_to_l1(self, chunk_text: str) -> dict:
        """
        Breaks down L0 summarization into smaller, more manageable tasks for the LLM,
        then assembles the JSON in Python.
        """
        # Step 1: Generate Diary Entry
        diary_prompt = self.prompts.format("l1_diary_entry", text=chunk_text)
        diary_entry_text = self.ollama.generate_completion(diary_prompt)
        diary_entry_text = self._clean_llm_output(diary_entry_text)

        if not diary_entry_text:
            print("    - WARNING: Failed to generate diary entry. Skipping chunk.")
            return {}

        # Step 2: Extract Key Facts (Bullets and Rules) from the diary entry
        bullets_prompt = self.prompts.format("l1_bullets", diary_entry=diary_entry_text)
        bullets_text = self.ollama.generate_completion(bullets_prompt)
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

        # Assemble the L1 JSON object in Python
        l1_data = {
            "id": f"l1_{int(time.time())}",
            "diary_entry": diary_entry_text,
            "bullets": sorted(list(set(bullets))),
            "rules_locked": sorted(list(set(rules_locked))),
            "timestamp": str(time.time())
        }
        return l1_data

    def update_master(self, master_json: str, new_l1_json: str) -> str:
        prompt = self.prompts.format("master_updater", master_json=master_json, new_l1_json=new_l1_json)
        return self.ollama.generate_completion(prompt)
