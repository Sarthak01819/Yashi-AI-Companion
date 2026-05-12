"""
Semantic memory — store and retrieve memories by meaning using embeddings.
Embeddings stored as BLOBs in SQLite; cosine similarity done in-process.
"""

import time
import struct
import logging
import numpy as np
from typing import List, Tuple, Optional

from core.memory.database import db_cursor
from config.settings import EMBEDDING_MODEL, MAX_SEMANTIC_RESULTS

logger = logging.getLogger(__name__)
_model = None
EXPECTED_DIM = 384   # all-MiniLM-L6-v2 output dimension


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def _encode(text: str) -> np.ndarray:
    return _get_model().encode(text, normalize_embeddings=True, show_progress_bar=False)


def _vec_to_blob(vec: np.ndarray) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec.tolist())


def _blob_to_vec(blob: bytes) -> Optional[np.ndarray]:
    """Decode blob to float32 array. Returns None if corrupt/wrong size."""
    n = len(blob) // 4
    if n != EXPECTED_DIM:
        return None   # skip malformed entries
    return np.array(struct.unpack(f"{n}f", blob), dtype=np.float32)


def store_memory(content: str, source: str = "conversation") -> int:
    vec  = _encode(content)
    blob = _vec_to_blob(vec)
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO memory_vectors (content, source, vector_blob, timestamp)"
            " VALUES (?,?,?,?)",
            (content, source, blob, time.time()),
        )
        return cur.lastrowid


def search_memory(
    query: str,
    top_k: int = MAX_SEMANTIC_RESULTS,
    min_score: float = 0.40,
) -> List[Tuple[str, float]]:
    """Return list of (content, score) sorted by relevance."""
    q_vec = _encode(query)

    with db_cursor() as cur:
        cur.execute("SELECT content, vector_blob FROM memory_vectors")
        rows = cur.fetchall()

    if not rows:
        return []

    results = []
    skipped = 0
    for row in rows:
        db_vec = _blob_to_vec(row["vector_blob"])
        if db_vec is None:
            skipped += 1
            continue
        score = float(np.dot(q_vec, db_vec))
        if score >= min_score:
            results.append((row["content"], score))

    if skipped:
        logger.debug("Skipped %d malformed memory vectors", skipped)

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


def store_fact(category: str, fact: str, confidence: float = 1.0) -> None:
    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO personal_facts (category, fact, confidence, timestamp)
               VALUES (?,?,?,?)
               ON CONFLICT(fact) DO UPDATE SET
                   confidence=excluded.confidence,
                   timestamp=excluded.timestamp""",
            (category, fact, confidence, time.time()),
        )
    store_memory(f"[FACT:{category}] {fact}", source="fact")


def get_all_facts(category: Optional[str] = None) -> List[dict]:
    with db_cursor() as cur:
        if category:
            cur.execute(
                "SELECT category, fact, confidence FROM personal_facts"
                " WHERE category=? ORDER BY timestamp DESC",
                (category,),
            )
        else:
            cur.execute(
                "SELECT category, fact, confidence FROM personal_facts"
                " ORDER BY timestamp DESC"
            )
        return [dict(r) for r in cur.fetchall()]
