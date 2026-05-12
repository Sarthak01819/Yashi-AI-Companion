"""
Voice energy / prosody analysis.
Computes RMS energy and zero-crossing rate from raw PCM audio frames.
"""

import numpy as np
from typing import Optional


def compute_energy(audio_np: np.ndarray) -> float:
    """RMS energy normalised to [0, 1]."""
    if audio_np.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio_np.astype(np.float32) ** 2)) / 32768.0)


def compute_zcr(audio_np: np.ndarray) -> float:
    """Zero-crossing rate — higher = more tense/excited speech."""
    if audio_np.size < 2:
        return 0.0
    signs = np.sign(audio_np.astype(np.float32))
    crossings = np.sum(np.abs(np.diff(signs))) / 2
    return float(crossings / len(audio_np))


def classify_voice_emotion(energy: float, zcr: float) -> str:
    """Very rough voice emotion from energy + zcr."""
    if energy > 0.15 and zcr > 0.12:
        return "excited"
    elif energy > 0.10:
        return "engaged"
    elif energy < 0.03:
        return "quiet"
    elif zcr > 0.15:
        return "tense"
    return "neutral"
