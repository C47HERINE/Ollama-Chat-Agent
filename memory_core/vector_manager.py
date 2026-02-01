import chromadb
import requests
import json

class VectorManager:
    def __init__(self, collection_name="memory_bullets", host="http://localhost:11434", model="embeddinggemma"):
        self.client = chromadb.PersistentClient(path="./chroma_db_new") # Use a new, clean database
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.host = host
        self.model = model

    def _get_embedding(self, text, prefix=""):
        url = f"{self.host}/api/embeddings"
        payload = {"model": self.model, "prompt": f"{prefix}{text}"}
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            return response.json()["embedding"]
        except Exception as e:
            print(f"Error getting embedding: {e}")
            return None

    def index_bullets(self, l1_id, bullets):
        if not bullets:
            return

        # Process in batches to be safe
        batch_size = 50
        for i in range(0, len(bullets), batch_size):
            batch_bullets = bullets[i:i+batch_size]
            
            embeddings = []
            valid_bullets_in_batch = []
            for bullet in batch_bullets:
                emb = self._get_embedding(bullet, prefix="title: none | text: ")
                if emb:
                    embeddings.append(emb)
                    valid_bullets_in_batch.append(bullet)
            
            if not embeddings:
                continue

            ids = [f"{l1_id}_{i+j}" for j, _ in enumerate(valid_bullets_in_batch)]
            metadatas = [{"source_id": l1_id} for _ in valid_bullets_in_batch]
            
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=valid_bullets_in_batch
            )

    def search_and_vote(self, query, top_k_bullets=50, top_n_files=3):
        query_emb = self._get_embedding(query, prefix="task: search result | query: ")
        if not query_emb:
            return []

        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=top_k_bullets
        )

        if not results or not results.get('metadatas') or not results['metadatas'][0]:
            return []

        votes = {}
        for meta in results['metadatas'][0]:
            src_id = meta.get('source_id')
            if src_id:
                votes[src_id] = votes.get(src_id, 0) + 1
        
        sorted_files = sorted(votes.items(), key=lambda item: item[1], reverse=True)
        return [f[0] for f in sorted_files[:top_n_files]]
