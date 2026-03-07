"""
Create synthetic test audio with acoustically distinct healthy vs PD coughs.

Healthy cough:  broadband noise burst + high-freq harmonics
                → high spectral centroid (~4 000-6 000 Hz), high ZCR, fast rise
PD/severe cough: narrow-band low-frequency signal, slow decay
                → low centroid (~300-800 Hz), low ZCR, slow rise

These differences directly drive pd_classifier.pd_likelihood().
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from scipy.io import wavfile

_DIR = Path(__file__).resolve().parent

RNG = np.random.default_rng(42)  # fixed seed → reproducible features


def _cough_healthy(sr: int, duration: float = 0.30) -> np.ndarray:
    """
    Strong healthy cough: explosive broadband burst, fast decay.
    Spectral centroid ~4 000-6 000 Hz; ZCR ~0.30-0.45; rise time ~15-40 ms.
    """
    t = np.linspace(0, duration, int(sr * duration))
    # Broadband noise with very fast exponential attack/decay
    burst = RNG.standard_normal(len(t)) * np.exp(-25.0 * t)
    # Add high-frequency harmonics (1 kHz, 2 kHz, 3 kHz)
    for freq in (1000, 2000, 3000):
        burst += 0.25 * np.sin(2 * np.pi * freq * t) * np.exp(-18.0 * t)
    # Low-frequency tail (barely audible)
    tail = 0.08 * np.sin(2 * np.pi * 120 * t) * np.exp(-4.0 * t)
    return burst + tail


def _cough_moderate(sr: int, duration: float = 0.30) -> np.ndarray:
    """
    Moderate cough: mix of broadband and narrow-band, medium decay.
    Centroid ~2 000-3 000 Hz; ZCR ~0.18-0.25; rise time ~50-100 ms.
    """
    t = np.linspace(0, duration, int(sr * duration))
    broadband = RNG.standard_normal(len(t)) * 0.5 * np.exp(-10.0 * t)
    mid = 0.6 * np.sin(2 * np.pi * 500 * t) * np.exp(-8.0 * t)
    low = 0.3 * np.sin(2 * np.pi * 200 * t) * np.exp(-4.0 * t)
    return broadband + mid + low


def _cough_severe_pd(sr: int, duration: float = 0.30) -> np.ndarray:
    """
    Severe/PD cough: narrow-band low-frequency, slow decay.
    Centroid ~300-700 Hz; ZCR ~0.05-0.10; rise time ~120-220 ms.
    """
    t = np.linspace(0, duration, int(sr * duration))
    # Dominant low-frequency components — no high-freq energy
    fundamental = np.sin(2 * np.pi * 150 * t) * np.exp(-4.0 * t)
    sub = 0.4 * np.sin(2 * np.pi * 80 * t) * np.exp(-2.5 * t)
    # Minimal noise — PD voice is smooth/less turbulent
    noise = 0.015 * RNG.standard_normal(len(t))
    return fundamental + sub + noise


_COUGH_FN = {
    "healthy": _cough_healthy,
    "moderate": _cough_moderate,
    "severe": _cough_severe_pd,
}


def create_recording(patient_type: str, sr: int = 22050, num_coughs: int = 3) -> np.ndarray:
    """
    Embed `num_coughs` into a recording with silence padding.
    Each cough is normalised before embedding so the detector sees it clearly.
    """
    fn = _COUGH_FN[patient_type]
    silence_start = np.zeros(int(sr * 0.5))
    silence_gap = np.zeros(int(sr * 0.35))

    parts = [silence_start]
    for _ in range(num_coughs):
        cough = fn(sr=sr)
        peak = np.max(np.abs(cough))
        if peak > 0:
            cough = cough / peak * 0.85
        parts.append(cough)
        parts.append(silence_gap)

    recording = np.concatenate(parts)
    # Add very low background noise
    recording += 0.008 * RNG.standard_normal(len(recording))
    # Final normalise
    peak = np.max(np.abs(recording))
    if peak > 0:
        recording = recording / peak
    return recording


def main() -> None:
    sr = 22050
    audio_dir = _DIR / "audio"
    audio_dir.mkdir(exist_ok=True)

    patients = {"001": "healthy", "002": "moderate", "003": "severe"}

    for pid, ptype in patients.items():
        print(f"Patient {pid} ({ptype})...")
        audio = create_recording(ptype, sr=sr)
        path = audio_dir / f"patient_{pid}.wav"
        wavfile.write(str(path), sr, np.int16(audio * 32767))
        print(f"  saved {path}")

        # Also save a follow-up WAV for trend testing (patient_001 only)
        if pid == "001":
            audio2 = create_recording("moderate", sr=sr)  # simulate mild decline
            path2 = audio_dir / f"patient_{pid}_followup.wav"
            wavfile.write(str(path2), sr, np.int16(audio2 * 32767))
            print(f"  saved {path2}")

        try:
            import soundfile as sf
            from scipy.signal import resample as sci_resample
            opus_sr = 16000
            audio_opus = sci_resample(audio, int(len(audio) * opus_sr / sr))
            opus_path = audio_dir / f"patient_{pid}.opus"
            sf.write(str(opus_path), audio_opus, opus_sr, format="OGG", subtype="OPUS")
            print(f"  saved {opus_path}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
