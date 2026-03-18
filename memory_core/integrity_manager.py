import os
import json
import logging
import traceback
from .vector_manager import VectorManager

logger = logging.getLogger(__name__)

class MemoryIntegrityManager:
    def __init__(self, l1_dir, vector_manager: VectorManager):
        self.l1_dir = l1_dir
        self.vm = vector_manager

    def sync(self):
        logger.info("Starting Memory Integrity Sync...")
        try:
            if not os.path.exists(self.l1_dir):
                logger.warning(f"L1 directory not found: {self.l1_dir}")
                return

            files = [f for f in os.listdir(self.l1_dir) if f.endswith(".json")]
            
            for filename in files:
                self._sync_file(filename)
        
        except Exception as e:
            logger.error(f"An unexpected error occurred during sync: {e}")
            logger.error(traceback.format_exc())
        
        logger.info("Memory Integrity Sync Complete.")

    def _sync_file(self, filename):
        file_path = os.path.join(self.l1_dir, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            l1_id = data.get("id")
            bullets = data.get("bullets", [])
            
            if not l1_id:
                logger.warning(f"Skipping {filename}: No ID found.")
                return

            existing = self.vm.collection.get(where={"source_file": l1_id}, limit=1)
            if not existing['ids']:
                logger.info(f"Indexing missing file: {filename}")
                self.vm.add_to_index(bullets, l1_id)
            
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {filename}: {e}")
            logger.error(traceback.format_exc())
        except Exception as e:
            logger.error(f"Error processing file {filename}: {e}")
            logger.error(traceback.format_exc())
