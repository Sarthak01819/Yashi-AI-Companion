"""
Text-based sentiment analysis using a lightweight transformer pipeline.
Lazy-loaded to avoid startup cost. Falls back to keyword heuristic if model unavailable.
"""

import logging
import re
from typing import Dict

logger = logging.getLogger(__name__)
_pipeline = None

POSITIVE_KEYWORDS = {"happy", "great", "awesome", "love", "excited", "glad", "wonderful", "good", "fantastic", "joy", "thanks", "thank"}
NEGATIVE_KEYWORDS = {"sad", "bad", "terrible", "awful", "hate", "angry", "upset", "depressed", "anxious", "worried", "scared", "hurt", "pain", "lonely", "lost"}
NEUTRAL_KEYWORDS  = {"okay", "fine", "alright", "whatever", "normal", "usual"}


def _heuristic_sentiment(text: str) -> Dict:
    words = set(re.findall(r'\b\w+\b', text.lower()))
    pos = len(words & POSITIVE_KEYWORDS)
    neg = len(words & NEGATIVE_KEYWORDS)
    if neg > pos:
        return {"label": "NEGATIVE", "score": 0.6 + min(neg * 0.1, 0.35)}
    elif pos > neg:
        return {"label": "POSITIVE", "score": 0.6 + min(pos * 0.1, 0.35)}
    return {"label": "NEUTRAL", "score": 0.55}


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        try:
            from transformers import pipeline
            _pipeline = pipeline(
                "text-classification",
                model="distilbert-base-uncased-finetuned-sst-2-english",
                truncation=True,
                max_length=128,
                device=-1,  # CPU only
            )
            logger.info("Sentiment pipeline loaded.")
        except Exception as e:
            logger.warning("Sentiment model unavailable (%s), using heuristic.", e)
            _pipeline = "heuristic"
    return _pipeline


def analyse_sentiment(text: str) -> Dict:
    """Returns {'label': 'POSITIVE'|'NEGATIVE'|'NEUTRAL', 'score': float, 'emotion': str}"""
    if not text.strip():
        return {"label": "NEUTRAL", "score": 0.5, "emotion": "neutral"}

    pipe = _get_pipeline()
    if pipe == "heuristic":
        result = _heuristic_sentiment(text)
    else:
        try:
            result = pipe(text[:512])[0]
        except Exception:
            result = _heuristic_sentiment(text)

    # Map to fine-grained emotion
    label = result["label"]
    score = result["score"]

    if label == "NEGATIVE":
        if score > 0.85:
            emotion = "distressed"
        elif score > 0.65:
            emotion = "sad"
        else:
            emotion = "concerned"
    elif label == "POSITIVE":
        if score > 0.90:
            emotion = "joyful"
        elif score > 0.70:
            emotion = "happy"
        else:
            emotion = "content"
    else:
        emotion = "neutral"

    return {"label": label, "score": score, "emotion": emotion}
