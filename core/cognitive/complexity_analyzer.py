"""
Analyse the complexity/type of user input to determine cognitive load.
"""

import re
from typing import Dict
from config.settings import COMPLEXITY_KEYWORDS_DEEP, COMPLEXITY_KEYWORDS_LIGHT


def analyse_complexity(text: str) -> Dict:
    """
    Returns:
        complexity: float 0..1
        suggested_mode: "light" | "standard" | "deep" | "support"
        reasons: list of str
    """
    text_lower = text.lower()
    words = set(re.findall(r'\b\w+\b', text_lower))
    reasons = []

    deep_hits = [kw for kw in COMPLEXITY_KEYWORDS_DEEP if kw in text_lower]
    light_hits = [kw for kw in COMPLEXITY_KEYWORDS_LIGHT if kw in text_lower]

    # Word count factor
    word_count = len(text.split())
    length_score = min(word_count / 40, 1.0)

    # Question depth
    question_words = {"why", "how", "what", "explain", "describe", "tell me about"}
    has_deep_question = bool(question_words & words)

    # Emotion words
    emotion_distress_words = {
        "depressed", "anxious", "panic", "scared", "hopeless",
        "suicid", "hurt", "pain", "cry", "crying", "alone", "lonely"
    }
    has_distress = bool(emotion_distress_words & words)

    # Calculate
    deep_score = (
        len(deep_hits) * 0.25
        + length_score * 0.20
        + (0.20 if has_deep_question else 0)
        + (0.50 if has_distress else 0)
    )
    light_score = len(light_hits) * 0.40

    complexity = min(deep_score - light_score * 0.3, 1.0)
    complexity = max(complexity, 0.0)

    if has_distress:
        mode = "support"
        reasons.append("distress indicators detected")
    elif deep_score > 0.50:
        mode = "deep"
        reasons.append("complex/emotional topic")
    elif light_score >= 0.40:
        mode = "light"
        reasons.append("task/command intent")
    else:
        mode = "standard"

    return {
        "complexity": round(complexity, 3),
        "suggested_mode": mode,
        "reasons": reasons,
        "word_count": word_count,
    }
