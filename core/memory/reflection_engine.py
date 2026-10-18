"""
Reflection engine — periodically summarises conversations and extracts insights.
"""

import time
import logging
from typing import Optional

from core.memory.database import db_cursor
from core.memory.conversation_store import get_messages_since
from config.settings import REFLECTION_INTERVAL_MINUTES, REFLECTION_MIN_MESSAGES

logger = logging.getLogger(__name__)

_last_reflection: float = 0.0


def save_reflection(session_id: str, summary: str, insight: str, mood_trend: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO reflections (session_id, summary, insight, mood_trend, timestamp) VALUES (?,?,?,?,?)",
            (session_id, summary, insight, mood_trend, time.time()),
        )


def get_recent_reflections(limit: int = 3) -> list:
    with db_cursor() as cur:
        cur.execute(
            "SELECT summary, insight, mood_trend, timestamp FROM reflections ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


async def maybe_reflect(session_id: str, ollama_client, emotion_state: dict) -> Optional[str]:
    """Run reflection if enough time has passed and there are enough messages."""
    global _last_reflection
    now = time.time()
    interval_sec = REFLECTION_INTERVAL_MINUTES * 60

    if now - _last_reflection < interval_sec:
        return None

    since = _last_reflection if _last_reflection else now - interval_sec
    messages = get_messages_since(since, session_id)
    if len(messages) < REFLECTION_MIN_MESSAGES:
        return None

    _last_reflection = now

    # Build a compact transcript
    transcript = "\n".join(
        f"{m['role'].upper()}: {m['content'][:200]}"
        for m in messages[-20:]
    )

    prompt = (
        "You are an introspective AI assistant. Analyse this recent conversation excerpt "
        "and provide:\n1. A 2-sentence summary\n2. One key insight about the user\n"
        "3. The overall mood trend (positive/neutral/concerned)\n\n"
        f"Conversation:\n{transcript}\n\n"
        "Reply in this exact format:\nSUMMARY: ...\nINSIGHT: ...\nMOOD: ..."
    )

    try:
        response = await ollama_client.generate(prompt, mode="light")
        lines = {
            k.strip(): v.strip()
            for line in response.strip().splitlines()
            if ":" in line
            for k, v in [line.split(":", 1)]
        }
        summary = lines.get("SUMMARY", "Conversation analysed.")
        insight = lines.get("INSIGHT", "")
        mood = lines.get("MOOD", emotion_state.get("emotional_state", "neutral"))

        save_reflection(session_id, summary, insight, mood)
        logger.info("Reflection stored: %s", summary[:80])

        # Save insight as a memory vector
        from core.memory.semantic_memory import store_memory
        store_memory(f"[REFLECTION] {summary} {insight}", source="reflection")

        return summary
    except Exception as e:
        logger.warning("Reflection failed: %s", e)
        return None
