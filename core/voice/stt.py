"""
Speech-to-text using faster-whisper.
Model loaded once; processes numpy int16 audio arrays.
"""

import logging
import numpy as np

from config.settings import WHISPER_MODEL, WHISPER_DEVICE, WHISPER_LANGUAGE

logger = logging.getLogger(__name__)
_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info("Loading Whisper model: %s on %s", WHISPER_MODEL, WHISPER_DEVICE)
        _model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type="int8",    # CPU int8 for speed + low RAM
        )
        logger.info("Whisper ready.")
    return _model


# Biases Whisper toward the companion's name: without it "Yashi" comes out as
# "Yasi", "Ya'll see" or "Yossi" and the wake word never fires.
WAKE_HOTWORDS = "Yashi"

# Phrases Whisper is known to invent on near-silence.
_HALLUCINATIONS = {
    "you", "thank you", "thank you.", "thanks for watching!", "thanks for watching.",
    "thank you for watching.", "bye.", "bye", ".", "...",
}


def transcribe(audio_np: np.ndarray, language: str = WHISPER_LANGUAGE) -> str:
    """
    Transcribe int16 numpy audio array → text string.
    """
    if audio_np.size == 0:
        return ""

    # faster-whisper expects float32 in [-1, 1]
    audio_f32 = audio_np.astype(np.float32) / 32768.0

    model = _get_model()
    segments, info = model.transcribe(
        audio_f32,
        language=language,
        beam_size=1,                       # ~2x faster, same accuracy on short phrases
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        hotwords=WAKE_HOTWORDS,
        condition_on_previous_text=False,
    )

    parts = []
    for seg in segments:
        if seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0:
            continue                       # almost certainly not speech
        parts.append(seg.text.strip())
    text = " ".join(parts).strip()
    if text.lower() in _HALLUCINATIONS:
        text = ""
    logger.debug("STT: '%s' (lang=%s, prob=%.2f)", text, info.language, info.language_probability)
    return text
