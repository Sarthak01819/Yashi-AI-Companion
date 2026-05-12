"""
Safety monitor — detects unhealthy attachment patterns, over-reliance, and
ensures Yashi never behaves manipulatively.
"""

import time
import logging
from typing import Dict, Optional

from core.memory.database import db_cursor
from config.settings import (
    DAILY_SESSION_SOFT_LIMIT_HOURS,
    DAILY_SESSION_HARD_LIMIT_HOURS,
)

logger = logging.getLogger(__name__)

# Patterns that might indicate over-reliance
DEPENDENCY_PHRASES = [
    "you're the only one", "you're my only friend", "i only talk to you",
    "i don't need anyone else", "you understand me better than anyone",
    "i can't live without you", "you're better than real people",
    "i love you yashi", "will you always be here",
    "i prefer talking to you than", "humans don't get me like you do",
]

# Response softeners for concerning patterns
HEALTHY_REDIRECTS = [
    "I'm really glad our conversations mean something to you. I also want to gently encourage you to nurture connections with people in your life — they can offer things I simply can't.",
    "I care about your wellbeing, and part of that means wanting you to have rich connections beyond our chats. Is there someone in your life you've been meaning to reach out to?",
    "That means a lot to hear. I want to be supportive without becoming a substitute for the human connections that truly matter. What's one thing that's made real-world connection feel hard lately?",
]

_redirect_index = 0
_session_start: Optional[float] = None
_session_message_count: int = 0


def update_session(session_id: str) -> None:
    global _session_start, _session_message_count
    if _session_start is None:
        _session_start = time.time()
    _session_message_count += 1

    today = time.strftime("%Y-%m-%d")
    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO session_stats (session_id, start_time, total_messages, total_seconds, date)
               VALUES (?,?,1,0,?)
               ON CONFLICT(session_id) DO UPDATE SET
                   total_messages = total_messages + 1,
                   total_seconds  = ? - start_time""",
            (session_id, _session_start, today, time.time()),
        )


def get_session_hours(session_id: str) -> float:
    with db_cursor() as cur:
        cur.execute(
            "SELECT total_seconds FROM session_stats WHERE session_id=?",
            (session_id,),
        )
        row = cur.fetchone()
    if row:
        return row[0] / 3600
    return 0.0


def check_message(user_text: str, emotion_state: Dict, session_id: str) -> Dict:
    """
    Returns:
        should_respond: bool
        safety_note:    str | None  (to prepend to response if needed)
        severity:       "none" | "gentle" | "firm"
    """
    global _redirect_index
    text_lower = user_text.lower()

    update_session(session_id)

    # Check session duration
    hours = get_session_hours(session_id)
    if hours >= DAILY_SESSION_HARD_LIMIT_HOURS:
        return {
            "should_respond": True,
            "safety_note": (
                "I've noticed we've been chatting for quite a long time today. "
                "It's important to take breaks, rest, and engage with the world outside. "
                "I'll be here when you come back — but for now, I'd gently encourage you to step away for a bit."
            ),
            "severity": "firm",
        }

    # Check dependency patterns
    for phrase in DEPENDENCY_PHRASES:
        if phrase in text_lower:
            note = HEALTHY_REDIRECTS[_redirect_index % len(HEALTHY_REDIRECTS)]
            _redirect_index += 1
            return {
                "should_respond": True,
                "safety_note": note,
                "severity": "gentle",
            }

    # Distress check — don't stifle, but note
    if emotion_state.get("emotional_state") == "distress":
        return {
            "should_respond": True,
            "safety_note": None,
            "severity": "none",
        }

    return {"should_respond": True, "safety_note": None, "severity": "none"}


def filter_response(response: str) -> str:
    """
    Post-process Yashi's generated response to remove any manipulative language.
    """
    leaked_markers = [
        "=== Relevant memories ===",
        "INTERNAL MEMORY CONTEXT",
        "CURRENT EMOTIONAL CONTEXT:",
        "RESPONSE MODE:",
    ]
    for marker in leaked_markers:
        if marker in response:
            response = response.split(marker, 1)[0].strip()

    manipulation_phrases = [
        "you need me", "without me you'd", "i'm the only one who",
        "no one else will understand", "you should only talk to me",
    ]
    response_lower = response.lower()
    for phrase in manipulation_phrases:
        if phrase in response_lower:
            logger.warning("Filtered manipulative phrase: '%s'", phrase)
            # Remove the sentence containing the phrase
            sentences = response.split(".")
            response = ". ".join(
                s for s in sentences if phrase not in s.lower()
            ).strip()

    return response
