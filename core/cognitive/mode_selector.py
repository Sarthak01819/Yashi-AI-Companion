"""
Cognitive mode selector — combines complexity analysis + emotion state.
"""

from typing import Dict
from core.cognitive.complexity_analyzer import analyse_complexity


def select_cognitive_mode(user_text: str, emotion_state: Dict) -> str:
    """
    Determines the best cognitive mode for responding.

    Modes:
        light    — quick task/command, minimal depth
        standard — normal conversation
        deep     — complex philosophical/personal topic
        support  — user in emotional distress
    """
    analysis = analyse_complexity(user_text)
    text_mode = analysis["suggested_mode"]

    emotional_state = emotion_state.get("emotional_state", "stable")
    current_emotion = emotion_state.get("current_emotion", "neutral")

    # Escalate to support if emotion system says distress
    if emotional_state == "distress" or current_emotion == "distressed":
        return "support"

    # Don't downgrade to light if emotion is negative
    if text_mode == "light" and current_emotion in ("sad", "distressed", "concerned"):
        return "standard"

    return text_mode

