"""
Audio capture: 16 kHz mono WAV, no auto-gain.
Task A: 5 s sustained vowel. Task B: 15 s spontaneous speech.
"""
import io
import wave
import sounddevice as sd
import numpy as np

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = np.float32
TASK_A_DURATION = 5.0
TASK_B_DURATION = 15.0
TRIM_SEC = 0.5


def _record_seconds(seconds: float) -> np.ndarray:
    """Record for given duration at 16 kHz mono. No gain applied."""
    samples = int(seconds * SAMPLE_RATE)
    rec = sd.rec(samples, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE)
    sd.wait()
    return rec.squeeze()


def record_seconds(seconds: float) -> np.ndarray:
    """Record for given duration (e.g. quick test). 16 kHz mono."""
    return _record_seconds(seconds)


def get_default_input_device_info() -> str:
    """Return default input device name for diagnostics when mic fails."""
    try:
        idx = sd.default.device[0]
        devs = sd.query_devices(idx)
        return f"{devs.get('name', '?')} (index {idx})"
    except Exception:
        return "unknown"


def record_task_a_sustained_vowel() -> np.ndarray:
    """5-second sustained vowel. Returns raw samples (no VAD)."""
    return _record_seconds(TASK_A_DURATION)


def record_task_b_spontaneous() -> np.ndarray:
    """15-second spontaneous speech. Returns raw samples (VAD in preprocessor)."""
    return _record_seconds(TASK_B_DURATION)


def trim_first_last(samples: np.ndarray, sec: float = TRIM_SEC) -> np.ndarray:
    """Trim first and last `sec` seconds. Used for Task A only."""
    n = int(sec * SAMPLE_RATE)
    if len(samples) <= 2 * n:
        return samples
    return samples[n:-n]


def samples_to_wav_bytes(samples: np.ndarray) -> bytes:
    """Convert float32 [-1,1] to 16-bit PCM WAV bytes."""
    samples = np.clip(samples, -1.0, 1.0)
    int16 = (samples * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(int16.tobytes())
    return buf.getvalue()
