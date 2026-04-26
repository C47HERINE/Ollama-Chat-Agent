import os
import chromadb
import requests
import traceback
from collections import Counter


class VectorManager:
    """Handles embedding, storage, and retrieval using ChromaDB."""

    def __init__(self, collection_name="memory_bullets", host=None, model="embeddinggemma"):
        """Initialize ChromaDB client and embedding API settings."""
        try:
            # Persistent local ChromaDB storage
            self.client = chromadb.PersistentClient(path="./user/chroma_db_new")

            # Collection setup
            self.collection_name = collection_name
            self.collection = self.client.get_or_create_collection(name=self.collection_name)

            # Embedding API config (Ollama or similar)
            self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            self.model = model

        except Exception as e:
            print(e, traceback.format_exc())
            raise

    def _get_embedding(self, text, prefix=""):
        """Generate embedding vector from text using external API."""
        try:
            url = f"{self.host}/api/embed"
            payload = {"model": self.model, "prompt": f"{prefix}{text}"}
            response = requests.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("embedding") or (data.get("embeddings") or [None])[0]

        except requests.exceptions.RequestException as e:
            print(e, traceback.format_exc())
            return None

        except Exception as e:
            print(e, traceback.format_exc())
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
                return

            # Generate unique IDs per bullet
            ids = [f"{file_id}_{i}" for i in range(len(valid_embeddings))]

            # Attach metadata for later grouping (voting)
            metadatas = [{"source_file": file_id} for _ in valid_embeddings]

            # Insert or update in ChromaDB
            self.collection.upsert(ids=ids, embeddings=valid_embeddings, metadatas=metadatas, documents=valid_bullets)

        except Exception as e:
            print(e, traceback.format_exc())


    def search_and_vote(self, query: str, top_k_bullets: int = 50, top_n_files: int = 3) -> list[str]:
        """Search similar bullets and return top source files via majority vote."""
        try:
            prefix = "task: search result | query: "

            # Embed query
            query_emb = self._get_embedding(query, prefix=prefix)
            if not query_emb:
                return []

            # Retrieve top matching bullets
            results = self.collection.query(query_embeddings=[query_emb], n_results=top_k_bullets)

            # Validate results structure
            if not results or not results.get('ids') or not results['ids'][0]:
                return []

            # Extract source_file metadata from results
            metadatas = results.get('metadatas', [[]])[0]
            source_files = [meta.get('source_file') for meta in metadatas if meta and meta.get('source_file')]
            if not source_files:
                return []

            # Count occurrences of each file (voting)
            vote_counts = Counter(source_files)

            # Select top files by frequency
            top_files = [item[0] for item in vote_counts.most_common(top_n_files)]
            return top_files

        except Exception as e:
            print(e, traceback.format_exc())
            return []


    def reset_collection(self):
        """Delete and recreate the ChromaDB collection."""
        try:
            # Drop collection
            self.client.delete_collection(name=self.collection_name)

            # Recreate empty collection
            self.collection = self.client.get_or_create_collection(name=self.collection_name)
        except Exception as e:
            print(e, traceback.format_exc())