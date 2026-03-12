import logging
import traceback
from collections import Counter

import chromadb
import requests

logger = logging.getLogger(__name__)

class VectorManager:
    def __init__(self, collection_name="memory_bullets", host="http://localhost:11434", model="embeddinggemma", request_timeout_s: float = 8.0):
        try:
            self.client = chromadb.PersistentClient(path="./chroma_db_new")
            self.collection_name = collection_name # Store collection name
            self.collection = self.client.get_or_create_collection(name=self.collection_name)
            self.host = host
            self.model = model
            self.request_timeout_s = request_timeout_s
        except Exception as e:
            logger.error(f"Failed to initialize VectorManager: {e}")
            logger.error(traceback.format_exc())
            raise

    def _get_embedding(self, text, prefix=""):
        try:
            url = f"{self.host}/api/embeddings"
            payload = {"model": self.model, "prompt": f"{prefix}{text}"}
            response = requests.post(url, json=payload, timeout=self.request_timeout_s)
            response.raise_for_status()
            return response.json()["embedding"]
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for embedding: {e}")
            logger.error(traceback.format_exc())
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred in _get_embedding: {e}")
            logger.error(traceback.format_exc())
            return None

    def add_to_index(self, bullets: list[str], file_id: str):
        try:
            if not bullets:
                return

            prefix = "title: none | text: "
            embeddings = [self._get_embedding(bullet, prefix=prefix) for bullet in bullets]
            
            valid_bullets = [b for i, b in enumerate(bullets) if embeddings[i] is not None]
            valid_embeddings = [emb for emb in embeddings if emb is not None]

            if not valid_embeddings:
                logger.warning(f"No valid embeddings generated for file {file_id}.")
                return

            ids = [f"{file_id}_{i}" for i in range(len(valid_embeddings))]
            metadatas = [{"source_file": file_id} for _ in valid_embeddings]
            
            if len(valid_bullets) != len(valid_embeddings):
                logger.warning(
                    "Mismatch between valid bullets and embeddings for file %s (bullets=%s, embeddings=%s)",
                    file_id,
                    len(valid_bullets),
                    len(valid_embeddings),
                )

            self.collection.upsert(
                ids=ids,
                embeddings=valid_embeddings,
                metadatas=metadatas,
                documents=valid_bullets
            )
            logger.info(f"Embedded {len(valid_embeddings)} bullets for file {file_id}")
        except Exception as e:
            logger.error(f"Failed to add to index for file {file_id}: {e}")
            logger.error(traceback.format_exc())

    def search_and_vote(self, query: str, top_k_bullets: int = 50, top_n_files: int = 3) -> list[str]:
        try:
            prefix = "task: search result | query: "
            query_emb = self._get_embedding(query, prefix=prefix)
            if not query_emb:
                logger.warning("Could not generate query embedding. Aborting search.")
                return []

            results = self.collection.query(
                query_embeddings=[query_emb],
                n_results=top_k_bullets
            )
            
            if not results or not results.get('ids') or not results['ids'][0]:
                logger.info("Vector search returned no results.")
                return []

            logger.info(f"Vector search returned {len(results['ids'][0])} initial candidates.")

            metadatas = results.get('metadatas', [[]])[0]
            source_files = [meta.get('source_file') for meta in metadatas if meta and meta.get('source_file')]
            
            if not source_files:
                logger.warning("Vector search results were found, but they contained no 'source_file' metadata.")
                return []

            vote_counts = Counter(source_files)
            top_files = [item[0] for item in vote_counts.most_common(top_n_files)]
            
            logger.info(f"Voting resulted in top {len(top_files)} files: {top_files}")
            return top_files
            
        except Exception as e:
            logger.error(f"Failed during search and vote for query '{query[:50]}...': {e}")
            logger.error(traceback.format_exc())
            return []

    def reset_collection(self):
        try:
            logger.info(f"Attempting to delete ChromaDB collection: {self.collection_name}")
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.get_or_create_collection(name=self.collection_name) # Re-create empty collection
            logger.info(f"ChromaDB collection '{self.collection_name}' reset successfully.")
        except Exception as e:
            logger.error(f"Failed to reset ChromaDB collection '{self.collection_name}': {e}")
            logger.error(traceback.format_exc())
