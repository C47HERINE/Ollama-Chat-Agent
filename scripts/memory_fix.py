import json
import os
import re
from typing import List, Dict

# This is a placeholder for the OllamaChatbot class
class OllamaChatbot:
    def ask_messages(self, messages, stream_to_console=False):
        # In a real implementation, this would make a call to the Ollama API
        print("--- Ollama Call ---")
        for msg in messages:
            print(f"[{msg['role']}]")
            print(msg['content'])
        print("--------------------")
        if "l1_diary_user" in messages[1]["content"]:
            return "I learned that the sky is blue."
        else:
            return "- The sky is blue."

class Summarizer:
    def __init__(self, llm):
        self.llm = llm
        with open("C:/Users/emond/Documents/Ollama-Chat-Agent/config/prompts.json") as f:
            self.prompts = json.load(f)

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

    def run(self, messages: List[Dict[str, str]]) -> Dict[str, str]:
        chat_history = "\n".join([f"{m['sender']}: {m['text']}" for m in messages])

        # Step 1: Generate Diary Entry
        system_prompt = self.prompts["l1_diary_system"]
        user_prompt = self.prompts["l1_diary_user"].format(text=chat_history)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        diary_entry_text = self.llm.ask_messages(messages, stream_to_console=False)
        diary_entry_text = self._clean_llm_output(diary_entry_text)

        # Step 2: Extract Key Facts
        system_prompt = self.prompts["l1_bullets_system"]
        user_prompt = self.prompts["l1_bullets_user"].format(diary_entry=diary_entry_text)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        bullets_text = self.llm.ask_messages(messages, stream_to_console=False)
        bullets_text = self._clean_llm_output(bullets_text)
        
        bullets = [line.strip()[1:].strip() for line in bullets_text.split('\n') if line.strip().startswith('-')]

        return {"diary": diary_entry_text, "bullets": bullets}

class MockChromaDB:
    def __init__(self):
        self.collection = {}

    def get_or_create_collection(self, name):
        return self

    def upsert(self, ids, documents, metadatas):
        for i, id in enumerate(ids):
            self.collection[id] = {"document": documents[i], "metadata": metadatas[i]}
    
    def get(self, ids):
        results = {"documents": [], "metadatas": []}
        for id in ids:
            if id in self.collection:
                results["documents"].append(self.collection[id]["document"])
                results["metadatas"].append(self.collection[id]["metadata"])
        return results

class VectorStore:
    def __init__(self):
        self.client = MockChromaDB()
        self.collection = self.client.get_or_create_collection(name="memory_bullets")

    def _get_embedding(self, text, prefix=""):
        # This is a mock embedding function
        return [0.1] * 768

    def add_bullets(self, bullets: List[str], file_id: str):
        print(f"Indexing bullets for file {file_id}:")
        if not bullets:
            return

        embeddings = []
        for bullet in bullets:
            emb = self._get_embedding(bullet, prefix="title: none | text: ")
            if emb:
                embeddings.append(emb)
        
        if not embeddings:
            return

        ids = [f"{file_id}_{i}" for i, _ in enumerate(bullets)]
        metadatas = [{"source_id": file_id} for _ in bullets]
        
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=bullets
        )
        print(f"  - Indexed {len(bullets)} bullets.")

class IntegrityCheck:
    def __init__(self, vector_store):
        self.vector_store = vector_store

    def run(self):
        print("Running integrity check...")
        # This is a placeholder for the actual integrity check logic.
        # In a real implementation, this would:
        # 1. Get all file IDs from the user/chats/.../l1/ directory.
        # 2. For each file ID, get the bullets from the file.
        # 3. Check that each bullet exists in the ChromaDB collection.
        
        # Mock check:
        test_file_id = "test_chat"
        test_bullets = ["The sky is blue."]
        ids_to_check = [f"{test_file_id}_{i}" for i, _ in enumerate(test_bullets)]
        
        results = self.vector_store.collection.get(ids=ids_to_check)
        
        if len(results["documents"]) == len(test_bullets):
            print("Integrity check passed for test_chat.")
        else:
            print("Integrity check failed for test_chat.")
        
        print("Integrity check complete.")


def validate_json(json_data: Dict[str, str]) -> bool:
    if "diary" not in json_data or "bullets" not in json_data:
        return False
    if not isinstance(json_data["diary"], str) or not isinstance(json_data["bullets"], list):
        return False
    return True

def save_to_disk(file_id: str, json_data: Dict[str, str]):
    # Placeholder for saving to disk
    # In a real implementation, this would save to user/chats/.../l1/*.json
    print(f"Saving data for file {file_id} to disk.")
    print(json.dumps(json_data, indent=2))

def main():
    chat_history = [
        {"sender": "user", "text": "What color is the sky?"},
        {"sender": "assistant", "text": "The sky is blue."},
    ]
    file_id = "test_chat"

    llm = OllamaChatbot()
    summarizer = Summarizer(llm)
    vector_store = VectorStore()
    integrity_check = IntegrityCheck(vector_store)

    summary_json = summarizer.run(chat_history)
    if validate_json(summary_json):
        vector_store.add_bullets(summary_json['bullets'], file_id)
        save_to_disk(file_id, summary_json)

    integrity_check.run()

if __name__ == "__main__":
    main()
