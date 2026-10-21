"""
Speech-to-text using faster-whisper.
Model loaded once; processes numpy int16 audio arrays.
"""

import logging
import re

import numpy as np

from config.settings import WAKE_THRESHOLD, WHISPER_MODEL, WHISPER_DEVICE, WHISPER_LANGUAGE

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


# Ways people open with her name. The acoustic check scores each one.
_WAKE_LEADS = (" Yashi", " Hey Yashi", " Okay Yashi", " Hi Yashi")
_PAD = np.zeros(4000, dtype=np.float32)    # 0.25 s: Whisper clips words at the very edge


def wake_score(audio_np: np.ndarray) -> float:
    """
    How likely it is that this audio STARTS with "Yashi" (0-1).

    Instead of trusting the transcript (Whisper often turns a lone "Yashi"
    into "Yes she" or drops it entirely), this asks the model directly: given
    the sound, what is the probability of the tokens for "Yashi"? It is the
    same forced alignment faster-whisper uses for word timestamps.
    """
    from faster_whisper.audio import pad_or_trim
    from faster_whisper.tokenizer import Tokenizer

    if audio_np.size == 0:
        return 0.0
    model = _get_model()
    audio = np.concatenate([_PAD, audio_np.astype(np.float32) / 32768.0, _PAD])
    features = model.feature_extractor(audio)
    frames = features.shape[-1]
    encoded = model.encode(pad_or_trim(features))
    tokenizer = Tokenizer(model.hf_tokenizer, True, task="transcribe", language="en")
    prompt = list(tokenizer.sot_sequence) + [tokenizer.no_timestamps]

    best = 0.0
    for lead in _WAKE_LEADS:
        result = model.model.align(encoded, prompt, [tokenizer.encode(lead)], frames)
        probs = np.asarray(result[0].text_token_probs, dtype=np.float64)
        if probs.size:
            best = max(best, float(np.exp(np.log(probs + 1e-9).mean())))
    return best


# Real English that sounds like her name. If Whisper confidently wrote one of
# these, only a very strong acoustic score still counts as "Yashi".
_SOUNDALIKE = re.compile(r"^\W*(?:yes|yeah|yah|ya|yea)\W+(?:she|shi|he)\b", re.I)


def is_wake(score: float, text: str = "") -> bool:
    if _SOUNDALIKE.match(text or ""):
        return score >= 0.1
    return score >= WAKE_THRESHOLD


def transcribe(audio_np: np.ndarray, language: str = WHISPER_LANGUAGE) -> str:
    """
    Transcribe int16 numpy audio array → text string.
    """
    if audio_np.size == 0:
        return ""

    # faster-whisper expects float32 in [-1, 1]
    audio_f32 = audio_np.astype(np.float32) / 32768.0
    short = audio_f32.size < 16000 * 6
    if short:
        audio_f32 = np.concatenate([_PAD, audio_f32, _PAD])

    model = _get_model()
    segments, info = model.transcribe(
        audio_f32,
        language=language,
        beam_size=5 if short else 1,       # short clips are cheap; a wider search fixes names
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
