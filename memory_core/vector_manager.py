import chromadb
import requests
import logging
import traceback
from collections import Counter

logger = logging.getLogger(__name__)


class VectorManager:
    """Handles embedding, storage, and retrieval using ChromaDB."""

    def __init__(self, collection_name="memory_bullets", host="http://localhost:11434", model="embeddinggemma"):
        """Initialize ChromaDB client and embedding API settings."""
        try:
            # Persistent local ChromaDB storage
            self.client = chromadb.PersistentClient(path="./chroma_db_new")

            # Collection setup
            self.collection_name = collection_name
            self.collection = self.client.get_or_create_collection(name=self.collection_name)

            # Embedding API config (Ollama or similar)
            self.host = host
            self.model = model
        except Exception as e:
            logger.error(f"Failed to initialize VectorManager: {e}")
            logger.error(traceback.format_exc())
            raise

    def _get_embedding(self, text, prefix=""):
        """Generate embedding vector from text using external API."""
        try:
            url = f"{self.host}/api/embeddings"

            # Prefix helps steer embedding context (e.g., query vs document)
            payload = {"model": self.model, "prompt": f"{prefix}{text}"}

            response = requests.post(url, json=payload)
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
        """Embed and store bullet points in ChromaDB under a file identifier."""
        try:
            if not bullets:
                return

            prefix = "title: none | text: "

            # Generate embeddings for all bullets
            embeddings = [self._get_embedding(bullet, prefix=prefix) for bullet in bullets]

            # Filter out failed embeddings
            valid_bullets = [b for i, b in enumerate(bullets) if embeddings[i] is not None]
            valid_embeddings = [emb for emb in embeddings if emb is not None]

            if not valid_embeddings:
                logger.warning(f"No valid embeddings generated for file {file_id}.")
                return

            # Generate unique IDs per bullet
            ids = [f"{file_id}_{i}" for i in range(len(valid_embeddings))]

            # Attach metadata for later grouping (voting)
            metadatas = [{"source_file": file_id} for _ in valid_embeddings]

            # Insert or update in ChromaDB
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
        """Search similar bullets and return top source files via majority vote."""
        try:
            prefix = "task: search result | query: "

            # Embed query
            query_emb = self._get_embedding(query, prefix=prefix)
            if not query_emb:
                logger.warning("Could not generate query embedding. Aborting search.")
                return []

            # Retrieve top matching bullets
            results = self.collection.query(
                query_embeddings=[query_emb],
                n_results=top_k_bullets
            )

            # Validate results structure
            if not results or not results.get('ids') or not results['ids'][0]:
                logger.info("Vector search returned no results.")
                return []

            logger.info(f"Vector search returned {len(results['ids'][0])} initial candidates.")

            # Extract source_file metadata from results
            metadatas = results.get('metadatas', [[]])[0]
            source_files = [
                meta.get('source_file')
                for meta in metadatas
                if meta and meta.get('source_file')
            ]

            if not source_files:
                logger.warning("Vector search results had no 'source_file' metadata.")
                return []

            # Count occurrences of each file (voting)
            vote_counts = Counter(source_files)

            # Select top files by frequency
            top_files = [item[0] for item in vote_counts.most_common(top_n_files)]

            logger.info(f"Voting resulted in top {len(top_files)} files: {top_files}")

            return top_files

        except Exception as e:
            logger.error(f"Failed during search and vote for query '{query[:50]}...': {e}")
            logger.error(traceback.format_exc())
            return []

    def reset_collection(self):
        """Delete and recreate the ChromaDB collection."""
        try:
            logger.info(f"Attempting to delete ChromaDB collection: {self.collection_name}")

            # Drop collection
            self.client.delete_collection(name=self.collection_name)

            # Recreate empty collection
            self.collection = self.client.get_or_create_collection(name=self.collection_name)

            logger.info(f"ChromaDB collection '{self.collection_name}' reset successfully.")

        except Exception as e:
            logger.error(f"Failed to reset ChromaDB collection '{self.collection_name}': {e}")
            logger.error(traceback.format_exc())