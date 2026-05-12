"""
core/memory/reflection_store.py
Persist and retrieve periodic reflections.
"""

import json
import logging
from typing import Dict, List, Optional
from core.memory.database import db_session

logger = logging.getLogger(__name__)


def save_reflection(
    session_id: str,
    summary: str,
    patterns: Optional[List[str]] = None,
    mood_trend: Optional[str] = None
) -> int:
    patterns_json = json.dumps(patterns or [])
    with db_session() as conn:
        cursor = conn.execute(
            """INSERT INTO reflections(session_id, summary, patterns, mood_trend)
               VALUES(?,?,?,?)""",
            (session_id, summary, patterns_json, mood_trend)
        )
        return cursor.lastrowid


def get_latest_reflections(limit: int = 3) -> List[Dict]:
    with db_session() as conn:
        rows = conn.execute(
            """SELECT summary, patterns, mood_trend, created_at
               FROM reflections ORDER BY created_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["patterns"] = json.loads(d["patterns"] or "[]")
        result.append(d)
    return result


def format_reflections_for_prompt() -> str:
    reflections = get_latest_reflections(2)
    if not reflections:
        return ""
    lines = []
    for r in reflections:
        lines.append(f"[{r['created_at']}] {r['summary']}")
        if r["mood_trend"]:
            lines.append(f"  Mood trend: {r['mood_trend']}")
    return "\n".join(lines)
