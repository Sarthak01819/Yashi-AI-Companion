"""
Conversation storage — save, retrieve, and manage dialogue history.
"""

import time
import logging
from typing import List, Dict, Optional

from core.memory.database import db_cursor
from config.settings import MAX_CONTEXT_MESSAGES

logger = logging.getLogger(__name__)


def save_message(session_id: str, role: str, content: str, emotion: str = "neutral") -> int:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (session_id, role, content, emotion, timestamp) VALUES (?,?,?,?,?)",
            (session_id, role, content, emotion, time.time()),
        )
        return cur.lastrowid


def get_recent_messages(session_id: str, limit: int = MAX_CONTEXT_MESSAGES) -> List[Dict]:
    with db_cursor() as cur:
        cur.execute(
            """SELECT role, content, emotion, timestamp
               FROM conversations
               WHERE session_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (session_id, limit),
        )
        rows = cur.fetchall()
    return [dict(r) for r in reversed(rows)]


def get_all_sessions() -> List[str]:
    with db_cursor() as cur:
        cur.execute("SELECT DISTINCT session_id FROM conversations ORDER BY MIN(timestamp)")
        return [r[0] for r in cur.fetchall()]


def count_today_messages(session_id: str) -> int:
    midnight = time.time() - (time.time() % 86400)
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM conversations WHERE session_id=? AND timestamp >= ?",
            (session_id, midnight),
        )
        return cur.fetchone()[0]


def get_messages_since(timestamp: float, session_id: Optional[str] = None) -> List[Dict]:
    with db_cursor() as cur:
        if session_id:
            cur.execute(
                "SELECT role, content, emotion, timestamp FROM conversations "
                "WHERE session_id=? AND timestamp >= ? ORDER BY timestamp",
                (session_id, timestamp),
            )
        else:
            cur.execute(
                "SELECT role, content, emotion, timestamp FROM conversations "
                "WHERE timestamp >= ? ORDER BY timestamp",
                (timestamp,),
            )
        return [dict(r) for r in cur.fetchall()]
