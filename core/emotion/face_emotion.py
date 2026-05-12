"""
Optional face emotion detection via OpenCV + FER.
Only activates if both packages are installed.

Install: pip install opencv-python fer

The FER library runs a mini CNN on a face crop — uses ~200 MB RAM when active.
GPU is NOT required (CPU inference is fast enough for 10 FPS).
"""

import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_available = False
_detector = None


def is_available() -> bool:
    global _available
    return _available


def _try_init():
    global _available, _detector
    if _detector is not None:
        return True
    try:
        import cv2
        from fer import FER
        _detector = FER(mtcnn=False)   # mtcnn=False = faster, uses Haar cascade
        _available = True
        logger.info("Face emotion detector ready (FER + OpenCV).")
        return True
    except ImportError:
        logger.debug("FER/OpenCV not installed — face emotion disabled.")
        return False
    except Exception as e:
        logger.warning("FER init failed: %s", e)
        return False


def analyse_frame(frame_bgr) -> Optional[Dict]:
    """
    Analyse a single BGR frame (numpy uint8 array from cv2.VideoCapture).
    Returns {'emotion': str, 'score': float, 'all': dict} or None.
    """
    if not _try_init():
        return None

    try:
        results = _detector.detect_emotions(frame_bgr)
        if not results:
            return None

        # Take the most prominent face
        emotions = results[0]["emotions"]
        dominant = max(emotions, key=emotions.get)
        score = emotions[dominant]

        return {
            "emotion": _fer_to_yashi(dominant),
            "score":    round(score, 3),
            "all":      emotions,
        }
    except Exception as e:
        logger.debug("FER frame error: %s", e)
        return None


def _fer_to_yashi(fer_label: str) -> str:
    """Map FER labels → Yashi emotion labels."""
    mapping = {
        "happy":    "happy",
        "sad":      "sad",
        "angry":    "concerned",
        "fear":     "distressed",
        "surprise": "excited",
        "disgust":  "concerned",
        "neutral":  "neutral",
    }
    return mapping.get(fer_label.lower(), "neutral")


class FaceEmotionCapture:
    """
    Background thread that captures webcam frames and updates emotion state.
    Usage:
        cap = FaceEmotionCapture()
        cap.start()
        emotion = cap.get_latest()  # {'emotion': 'happy', 'score': 0.92}
        cap.stop()
    """

    def __init__(self, camera_index: int = 0, fps: int = 8):
        self.camera_index = camera_index
        self.fps = fps
        self._latest: Optional[Dict] = None
        self._thread = None
        self._running = False

    def start(self) -> bool:
        if not _try_init():
            logger.info("FaceEmotionCapture: FER not available, skipping.")
            return False

        import threading
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def get_latest(self) -> Optional[Dict]:
        return self._latest

    def _loop(self):
        import cv2
        import time
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            logger.warning("Could not open camera %d", self.camera_index)
            return

        interval = 1.0 / self.fps
        while self._running:
            ret, frame = cap.read()
            if ret:
                result = analyse_frame(frame)
                if result:
                    self._latest = result
            time.sleep(interval)

        cap.release()
