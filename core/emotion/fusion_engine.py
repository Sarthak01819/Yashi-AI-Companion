"""
Emotion fusion engine.
Combines text sentiment + voice energy + history into a unified emotional state.
"""

import time
import logging
from collections import deque
from typing import Dict, Deque, Optional

from core.emotion.text_sentiment import analyse_sentiment
from core.emotion.voice_energy import compute_energy, compute_zcr, classify_voice_emotion
from config.settings import EMOTION_HISTORY_WINDOW

logger = logging.getLogger(__name__)

# Internal rolling history of emotion labels
_history: Deque[str] = deque(maxlen=EMOTION_HISTORY_WINDOW)

EMOTION_VALENCE = {
    "joyful": 1.0, "happy": 0.7, "content": 0.4, "excited": 0.6,
    "engaged": 0.2, "neutral": 0.0, "quiet": -0.1, "concerned": -0.3,
    "sad": -0.6, "tense": -0.4, "distressed": -0.9,
}


def fuse(text: str, audio_np=None) -> Dict:
    """
    Returns:
        current_emotion: str
        emotional_trend:  "positive" | "neutral" | "negative"
        emotional_state:  "stable" | "distress" | "positive"
        valence:          float -1..1
        text_sentiment:   dict
        voice_emotion:    str
    """
    text_result = analyse_sentiment(text)
    text_emotion = text_result["emotion"]

    voice_emotion = "neutral"
    if audio_np is not None:
        energy = compute_energy(audio_np)
        zcr = compute_zcr(audio_np)
        voice_emotion = classify_voice_emotion(energy, zcr)

    # Simple fusion: text has 70% weight, voice 30%
    text_val = EMOTION_VALENCE.get(text_emotion, 0.0)
    voice_val = EMOTION_VALENCE.get(voice_emotion, 0.0)
    fused_val = text_val * 0.7 + voice_val * 0.3

    # Map fused value back to label
    current_emotion = _valence_to_label(fused_val, text_emotion)
    _history.append(current_emotion)

    # Trend over window
    if len(_history) >= 3:
        avg = sum(EMOTION_VALENCE.get(e, 0.0) for e in _history) / len(_history)
        trend = "positive" if avg > 0.15 else "negative" if avg < -0.15 else "neutral"
    else:
        trend = "neutral"

    # State
    if fused_val < -0.55:
        state = "distress"
    elif fused_val > 0.40:
        state = "positive"
    else:
        state = "stable"

    return {
        "current_emotion": current_emotion,
        "emotional_trend":  trend,
        "emotional_state":  state,
        "valence":          round(fused_val, 3),
        "text_sentiment":   text_result,
        "voice_emotion":    voice_emotion,
    }


def get_emotion_history() -> list:
    return list(_history)


def _valence_to_label(val: float, text_emotion: str) -> str:
    if val >= 0.6:
        return "joyful"
    elif val >= 0.35:
        return "happy"
    elif val >= 0.15:
        return "content"
    elif val >= -0.15:
        return "neutral"
    elif val >= -0.45:
        return "concerned"
    elif val >= -0.70:
        return "sad"
    else:
        return "distressed"


# ── Optional face emotion integration ────────────────────────────────────────
_face_capture = None


def start_face_emotion(camera_index: int = 0) -> bool:
    """
    Start background webcam face emotion capture (requires opencv-python + fer).
    Call once at startup if you want face emotion included in fusion.
    """
    global _face_capture
    from core.emotion.face_emotion import FaceEmotionCapture
    _face_capture = FaceEmotionCapture(camera_index=camera_index)
    ok = _face_capture.start()
    if ok:
        logger.info("Face emotion capture started on camera %d", camera_index)
    return ok


def stop_face_emotion():
    global _face_capture
    if _face_capture:
        _face_capture.stop()
        _face_capture = None


def fuse_full(text: str, audio_np=None) -> Dict:
    """
    Full fusion: text + voice + face (if available).
    Drop-in replacement for fuse() when face emotion is running.
    """
    result = fuse(text, audio_np)

    if _face_capture:
        face_result = _face_capture.get_latest()
        if face_result:
            face_val  = EMOTION_VALENCE.get(face_result["emotion"], 0.0)
            face_conf = face_result["score"]
            # Blend: text 60%, voice 25%, face 15%
            blended = result["valence"] * 0.85 + face_val * face_conf * 0.15
            result["face_emotion"]  = face_result["emotion"]
            result["face_score"]    = face_conf
            result["valence"]       = round(blended, 3)
            result["current_emotion"] = _valence_to_label(blended, result["current_emotion"])

    return result
