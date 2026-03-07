"""
Preprocessor: Task A trim only. Task B: Silero VAD, strip silence (< 0.5), recombine.
No amplitude normalization (we track volume drops).
"""
import ssl
import numpy as np
import torch

SAMPLE_RATE = 16000
VAD_THRESHOLD = 0.5
# Silero expects 512 samples per chunk at 16 kHz
CHUNK_SAMPLES = 512


def _load_silero_vad():
    # On some Macs Python's SSL fails for torch.hub; use unverified context only for this fetch
    import urllib.request
    _ctx = ssl.create_default_context()
    _ctx.check_hostname = False
    _ctx.verify_mode = ssl.CERT_NONE
    _no_verify_opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_ctx)
    )
    _default_opener = urllib.request.build_opener()
    try:
        urllib.request.install_opener(_no_verify_opener)
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
            force_reload=False,
        )
    finally:
        urllib.request.install_opener(_default_opener)
    return model, utils


def trim_sustained_vowel(samples: np.ndarray, trim_sec: float = 0.5) -> np.ndarray:
    """Trim first and last trim_sec. For Task A only. No VAD."""
    n = int(trim_sec * SAMPLE_RATE)
    if len(samples) <= 2 * n:
        return samples
    return samples[n:-n]


def strip_silence_spontaneous(samples: np.ndarray) -> np.ndarray:
    """
    Run Silero VAD on Task B. Keep only frames where speech probability >= 0.5.
    Recombine voiced segments (concatenate).
    """
    model, (get_speech_timestamps, _, _, _, _) = _load_silero_vad()
    if not isinstance(samples, torch.Tensor):
        samples_t = torch.from_numpy(samples.astype(np.float32))
    else:
        samples_t = samples.float()
    timestamps = get_speech_timestamps(
        samples_t, model, sampling_rate=SAMPLE_RATE, threshold=VAD_THRESHOLD
    )
    if not timestamps:
        return np.array([], dtype=np.float32)
    out = []
    for seg in timestamps:
        start = seg["start"]
        end = seg["end"]
        out.append(samples[start:end])
    return np.concatenate(out).astype(np.float32)
