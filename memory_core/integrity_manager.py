import os
import json
from .vector_manager import VectorManager

class MemoryIntegrityManager:
    def __init__(self, l1_dir, vector_manager: VectorManager):
        self.l1_dir = l1_dir
        self.vm = vector_manager

    def sync(self):
        print("Starting Memory Integrity Sync...")
        # Get all indexed source_ids
        # Chroma doesn't have a direct "get all unique metadata values" efficiently, 
        # but we can iterate or just re-index missing ones.
        # For simplicity/robustness, we'll scan files and check if they are in DB.
        # A more optimized way would be to query all IDs, but let's assume we can just upsert.
        # Actually, upsert is idempotent. We can just re-index everything or check count.
        # To be smarter: check if file ID exists in collection.
        
        # Get all L1 files
        if not os.path.exists(self.l1_dir):
            print(f"L1 directory not found: {self.l1_dir}")
            return

        files = [f for f in os.listdir(self.l1_dir) if f.endswith(".json")]
        
        for filename in files:
            file_path = os.path.join(self.l1_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                l1_id = data.get("id")
                bullets = data.get("bullets", [])
                
                if not l1_id:
                    print(f"Skipping {filename}: No ID found.")
                    continue

                # Check if already indexed (naive check: query for one bullet or just upsert)
                # We will just upsert to ensure integrity. 
                # Optimization: Check if any doc with source_id exists.
                existing = self.vm.collection.get(where={"source_id": l1_id}, limit=1)
                if not existing['ids']:
                    print(f"Indexing missing file: {filename}")
                    self.vm.index_bullets(l1_id, bullets)
                
            except Exception as e:
                print(f"Error processing {filename}: {e}")
        print("Memory Integrity Sync Complete.")
