"""
core/memory/vector_store.py
Lightweight semantic memory using sentence-transformers + SQLite BLOB storage.
No external vector DB needed — keeps RAM usage minimal.
"""

import pickle
import logging
import numpy as np
from typing import List, Tuple, Optional
from functools import lru_cache

from core.memory.database import db_session
from config.settings import EMBEDDING_MODEL, VECTOR_TOP_K

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_encoder():
    """Lazy-load the embedding model once, cache it."""
    from sentence_transformers import SentenceTransformer
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    return model


def embed(text: str) -> np.ndarray:
    """Return a normalized float32 embedding vector."""
    encoder = _get_encoder()
    vec = encoder.encode(text, normalize_embeddings=True, show_progress_bar=False)
    return vec.astype(np.float32)


def store_memory(content: str, source_type: str = "conversation", source_id: Optional[int] = None):
    """Embed and store a piece of text in memory_vectors."""
    try:
        vec = embed(content)
        blob = pickle.dumps(vec)
        with db_session() as conn:
            conn.execute(
                """INSERT INTO memory_vectors(content, embedding, source_type, source_id)
                   VALUES(?,?,?,?)""",
                (content, blob, source_type, source_id)
            )
        logger.debug(f"Stored memory vector for: {content[:60]}")
    except Exception as e:
        logger.error(f"Failed to store memory: {e}")


def retrieve_similar(query: str, top_k: int = VECTOR_TOP_K) -> List[Tuple[str, float]]:
    """
    Retrieve the top_k most semantically similar memories.
    Returns list of (content, similarity_score) tuples.
    """
    try:
        query_vec = embed(query)

        with db_session() as conn:
            rows = conn.execute(
                "SELECT content, embedding FROM memory_vectors ORDER BY created_at DESC LIMIT 500"
            ).fetchall()

        if not rows:
            return []

        results = []
        for row in rows:
            stored_vec = pickle.loads(row["embedding"])
            # Cosine similarity (both normalized, so dot product = cosine)
            score = float(np.dot(query_vec, stored_vec))
            results.append((row["content"], score))

        # Sort by score descending, return top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    except Exception as e:
        logger.error(f"Vector retrieval failed: {e}")
        return []


def retrieve_similar_formatted(query: str, top_k: int = VECTOR_TOP_K) -> str:
    """Return memories as a formatted string for prompt injection."""
    memories = retrieve_similar(query, top_k)
    if not memories:
        return ""
    lines = [f"- {content} (relevance: {score:.2f})" for content, score in memories if score > 0.3]
    return "\n".join(lines)


def delete_old_vectors(keep_latest: int = 1000):
    """Prune oldest vectors to keep DB size manageable."""
    with db_session() as conn:
        conn.execute(
            """DELETE FROM memory_vectors
               WHERE id NOT IN (
                   SELECT id FROM memory_vectors
                   ORDER BY created_at DESC LIMIT ?
               )""",
            (keep_latest,)
        )
