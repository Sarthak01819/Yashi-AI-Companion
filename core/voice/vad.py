"""
Voice Activity Detection (VAD) — simple energy-based end-of-speech detection.
"""

import numpy as np
import time
from collections import deque
from typing import Optional
from config.settings import VAD_SILENCE_THRESHOLD, VAD_ENERGY_THRESHOLD, SAMPLE_RATE, AUDIO_CHUNK_SECONDS


class SimpleVAD:
    """
    Lightweight VAD that triggers end-of-speech when energy drops
    below threshold for VAD_SILENCE_THRESHOLD seconds.
    """

    def __init__(self):
        self.chunk_size = int(SAMPLE_RATE * AUDIO_CHUNK_SECONDS)
        self.silence_threshold = VAD_SILENCE_THRESHOLD
        self.energy_threshold = VAD_ENERGY_THRESHOLD
        self._silent_chunks = 0
        self._chunks_for_silence = int(self.silence_threshold / AUDIO_CHUNK_SECONDS)
        self._speech_started = False
        self._buffer = []

    def reset(self):
        self._silent_chunks = 0
        self._speech_started = False
        self._buffer = []

    def process_chunk(self, chunk: np.ndarray) -> dict:
        """
        Feed a chunk of audio. Returns:
            speech_detected: bool
            end_of_speech:   bool
            energy:          float
        """
        energy = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)) / 32768.0)
        is_speech = energy > self.energy_threshold

        if is_speech:
            self._speech_started = True
            self._silent_chunks = 0
            self._buffer.append(chunk)
        elif self._speech_started:
            self._silent_chunks += 1
            self._buffer.append(chunk)

        end_of_speech = (
            self._speech_started
            and self._silent_chunks >= self._chunks_for_silence
        )

        return {
            "speech_detected": self._speech_started,
            "end_of_speech":   end_of_speech,
            "energy":          energy,
        }

    def get_audio_buffer(self) -> np.ndarray:
        if not self._buffer:
            return np.array([], dtype=np.int16)
        return np.concatenate(self._buffer)
