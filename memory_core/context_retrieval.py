import math
import re
from collections import Counter
from typing import List, Tuple

import memory_core.helpers as helpers
import memory_core.paths as file_path


class ContextRetrieval:
    def __init__(self, chat_id):
        memory_paths = file_path.MemoryPaths(root=".", chat_id=chat_id)
        self.context_file_path = memory_paths.context_txt_path()
        self.context_text = helpers.read_text(self.context_file_path)
        self.stopwords = {
            "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is", "are", "was", "were",
            "it", "this", "that", "as", "at", "by", "be", "from", "you", "i", "we", "they", "he", "she",
        }
        self.token_pattern = re.compile(r"[a-z0-9_'-]{2,}")
        self.paragraph_split_pattern = re.compile(r"\n\s*\n")
        self.conversation_file = memory_paths.l0_active_path()

    # ----------------------------
    # Tokenization
    # ----------------------------

    def tokenize_text(self, text: str) -> List[str]:
        lowercase_text = text.lower()
        all_words = self.token_pattern.findall(lowercase_text)
        return [word for word in all_words if word not in self.stopwords]

    # ----------------------------
    # Scoring
    # ----------------------------

    def score_chunks_against_query(self, query_text: str, text_chunks: List[str]) -> List[Tuple[float, str]]:
        query_tokens = self.tokenize_text(query_text)
        if not query_tokens:
            return [(0.0, chunk) for chunk in text_chunks]

        query_token_counts = Counter(query_tokens)

        # Count how many chunks each token appears in
        document_frequencies = Counter()
        chunk_token_lists: List[List[str]] = []
        for chunk_text in text_chunks:
            tokens_in_chunk = self.tokenize_text(chunk_text)
            chunk_token_lists.append(tokens_in_chunk)
            for token in set(tokens_in_chunk):
                document_frequencies[token] += 1

        total_chunk_count = len(text_chunks) or 1
        scored_chunks: List[Tuple[float, str]] = []
        for chunk_text, tokens_in_chunk in zip(text_chunks, chunk_token_lists):
            token_frequencies = Counter(tokens_in_chunk)
            relevance_score = 0.0

            for token, query_count in query_token_counts.items():
                if token in token_frequencies:
                    inverse_document_frequency = (
                            math.log((total_chunk_count + 1) / (document_frequencies[token] + 1)) + 1.0)
                    relevance_score += (token_frequencies[token] * inverse_document_frequency
                                        * query_count * inverse_document_frequency)

            scored_chunks.append((relevance_score, chunk_text))

        scored_chunks.sort(key=lambda item: item[0], reverse=True)
        return scored_chunks

    # ----------------------------
    # Retrieval
    # ----------------------------

    def retrieve_relevant_context(self, query_text: str) -> str:
        max_character_budget = 8000
        minimum_chunk_length = 80
        raw_paragraphs = self.paragraph_split_pattern.split(self.context_text)
        text_chunks = [paragraph.strip() for paragraph in raw_paragraphs
                       if len(paragraph.strip()) >= minimum_chunk_length]

        ranked_chunks = self.score_chunks_against_query(query_text, text_chunks)
        selected_chunks: List[str] = []
        used_characters = 0

        for score, chunk_text in ranked_chunks:
            if score <= 0 and selected_chunks:
                break
            if used_characters + len(chunk_text) > max_character_budget:
                continue
            selected_chunks.append(chunk_text)
            used_characters += len(chunk_text)
            if used_characters >= max_character_budget:
                break

        return "\n\n---\n\n".join(selected_chunks)

    # ----------------------------
    # Public entry point
    # ----------------------------

    def build_context_from_conversation(self) -> str:
        conversation_data = helpers.read_json(self.conversation_file)
        if not conversation_data:
            return ""

        last_user_message = ""
        last_assistant_message = ""

        for entry in reversed(conversation_data):
            if entry.get("role") == "assistant" and not last_assistant_message:
                last_assistant_message = entry.get("content", "")
            elif entry.get("role") == "user" and not last_user_message:
                last_user_message = entry.get("content", "")

            if last_user_message and last_assistant_message:
                break

        query_text = f"{last_user_message} {last_assistant_message}".strip()
        return self.retrieve_relevant_context(query_text=query_text)
