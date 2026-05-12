"""
core/memory/facts_store.py
Extract, store and retrieve personal facts about the user.
Also manages narrative memory (long-arc user story).
"""

import re
import logging
from typing import List, Dict, Optional
from core.memory.database import db_session

logger = logging.getLogger(__name__)

# Simple rule-based fact extractor patterns
_FACT_PATTERNS = [
    # Name
    (r"\bmy name is ([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b", "name"),
    (r"\bcall me ([A-Z][a-z]+)\b", "name"),
    # Age
    (r"\bi(?:'m| am) (\d{1,2})(?: years old)?\b", "age"),
    # Location
    (r"\bi(?:'m| am) from ([A-Z][a-zA-Z\s,]+)\b", "location"),
    (r"\bi live in ([A-Z][a-zA-Z\s,]+)\b", "location"),
    # Job / Study
    (r"\bi(?:'m| am) a(?:n)? ([a-z]+(?: [a-z]+)?)\b", "occupation"),
    (r"\bi work as a(?:n)? ([a-z]+(?: [a-z]+)?)\b", "occupation"),
    (r"\bi study ([a-zA-Z\s]+)\b", "study_field"),
    # Preferences
    (r"\bi love ([a-zA-Z\s]+)\b", "interest"),
    (r"\bi enjoy ([a-zA-Z\s]+)\b", "interest"),
    (r"\bmy favorite (\w+) is ([a-zA-Z\s]+)\b", "preference"),
    # Goals
    (r"\bi want to ([a-zA-Z\s]+)\b", "goal"),
    (r"\bmy goal is to ([a-zA-Z\s]+)\b", "goal"),
    # Relationships
    (r"\bmy (partner|girlfriend|boyfriend|wife|husband|friend|best friend) ([A-Z][a-z]+)\b", "relationship"),
]


def extract_facts(text: str) -> List[Dict]:
    """Extract personal facts from a user message using regex patterns."""
    facts = []
    text_lower = text.lower()

    for pattern, category in _FACT_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            fact_value = match if isinstance(match, str) else " ".join(match)
            fact_value = fact_value.strip()
            if len(fact_value) > 2 and len(fact_value) < 120:
                facts.append({"category": category, "fact": fact_value})

    return facts


def save_facts(facts: List[Dict], source_msg_id: Optional[int] = None):
    """Upsert extracted facts into personal_facts table."""
    with db_session() as conn:
        for item in facts:
            try:
                conn.execute(
                    """INSERT INTO personal_facts(category, fact, source_msg)
                       VALUES(?,?,?)
                       ON CONFLICT(category, fact) DO UPDATE
                       SET updated_at=CURRENT_TIMESTAMP""",
                    (item["category"], item["fact"], source_msg_id)
                )
                logger.debug(f"Saved fact: [{item['category']}] {item['fact']}")
            except Exception as e:
                logger.warning(f"Fact insert failed: {e}")


def get_all_facts() -> List[Dict]:
    """Retrieve all personal facts."""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT category, fact, updated_at FROM personal_facts ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def format_facts_for_prompt() -> str:
    """Return a concise facts summary for the system prompt."""
    facts = get_all_facts()
    if not facts:
        return ""
    by_category: Dict[str, List[str]] = {}
    for f in facts:
        by_category.setdefault(f["category"], []).append(f["fact"])

    lines = []
    for cat, values in by_category.items():
        lines.append(f"• {cat.replace('_', ' ').title()}: {', '.join(values[:3])}")
    return "\n".join(lines)


# ── Narrative Memory ──────────────────────────────────────────────────────────

def upsert_narrative(content: str, chapter: int = 1):
    """Store or update the user's narrative chapter."""
    with db_session() as conn:
        existing = conn.execute(
            "SELECT id FROM narrative_memory WHERE chapter=?", (chapter,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE narrative_memory SET content=?, updated_at=CURRENT_TIMESTAMP WHERE chapter=?",
                (content, chapter)
            )
        else:
            conn.execute(
                "INSERT INTO narrative_memory(chapter, content) VALUES(?,?)",
                (chapter, content)
            )


def get_narrative() -> str:
    """Return all narrative chapters joined."""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT content FROM narrative_memory ORDER BY chapter ASC"
        ).fetchall()
    return "\n".join(r["content"] for r in rows)
