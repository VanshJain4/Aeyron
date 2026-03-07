"""
Emotional face structure aligned with Presage Face/MicroExpression.
Rolling variance and std of emotion confidence; configurable thresholds.
"""
from collections import deque
import math
import os

# Thresholds: breach when variance or std of emotion confidence exceeds these (tunable via env)
EMOTION_VARIANCE_THRESHOLD = float(os.environ.get("EMOTION_VARIANCE_THRESHOLD", "0.04"))
EMOTION_STD_THRESHOLD = float(os.environ.get("EMOTION_STD_THRESHOLD", "0.20"))
EMOTION_ROLLING_WINDOW = int(os.environ.get("EMOTION_ROLLING_WINDOW", "30"))


def _rolling_variance(values: deque) -> float:
    if len(values) < 2:
        return 0.0
    n = len(values)
    mean = sum(values) / n
    return sum((x - mean) ** 2 for x in values) / (n - 1)


def _rolling_std(values: deque) -> float:
    return math.sqrt(_rolling_variance(values))


class FaceEmotionBuffer:
    """Stores last N emotion confidence values; computes variance and std."""

    def __init__(self, maxlen: int = EMOTION_ROLLING_WINDOW):
        self._confidence: deque = deque(maxlen=maxlen)

    def push(self, confidence: float) -> None:
        self._confidence.append(max(0.0, min(1.0, confidence)))

    @property
    def variance(self) -> float:
        return _rolling_variance(self._confidence)

    @property
    def std(self) -> float:
        return _rolling_std(self._confidence)

    @property
    def mean(self) -> float:
        if not self._confidence:
            return 0.0
        return sum(self._confidence) / len(self._confidence)

    def variance_breach(self) -> bool:
        return len(self._confidence) >= 2 and self.variance >= EMOTION_VARIANCE_THRESHOLD

    def std_breach(self) -> bool:
        return len(self._confidence) >= 2 and self.std >= EMOTION_STD_THRESHOLD
