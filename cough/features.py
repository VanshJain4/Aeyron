"""
Feature extraction from cough segments.

8 features per cough:
  peak_to_decay_ratio, spectral_centroid, spectral_slope,
  rise_time, zero_crossing_rate, expulsive_duration,
  crest_factor, phase_power_ratio

Each segment is preprocessed (normalize + 6kHz lowpass) before feature
extraction to standardise across mic gain and recording conditions.
"""
from __future__ import annotations

import numpy as np
import librosa
from scipy.signal import butter, filtfilt


# ── Preprocessing ──────────────────────────────────────────────────────────

def _preprocess(segment: np.ndarray, sr: int) -> np.ndarray:
    """
    Normalize amplitude and lowpass-filter at 6 kHz.
    Removes high-frequency mic noise and standardises gain across recordings.
    """
    seg = segment.astype(np.float64)
    peak = np.max(np.abs(seg))
    if peak > 0:
        seg = seg / peak
    nyq = sr / 2.0
    if 6000.0 < nyq:
        b, a = butter(4, 6000.0 / nyq, btype="lowpass")
        seg = filtfilt(b, a, seg)
    return seg.astype(np.float32)


# ── Individual feature functions ───────────────────────────────────────────

def peak_to_decay_ratio(segment: np.ndarray) -> float:
    """Energy in first half (before peak) vs second half (after peak).
    Higher = stronger burst with quick decay."""
    abs_seg = np.abs(segment)
    peak_idx = int(np.argmax(abs_seg))
    first = segment[: peak_idx + 1]
    second = segment[peak_idx + 1 :]
    if len(first) == 0 or len(second) == 0:
        return 1.0
    rms_f = np.sqrt(np.mean(first ** 2))
    rms_s = np.sqrt(np.mean(second ** 2))
    return float(rms_f / rms_s) if rms_s > 0 else 100.0


def spectral_centroid_feature(segment: np.ndarray, sr: int = 22050) -> float:
    """Frequency-weighted mean of spectrum. Higher = more high-freq turbulence."""
    c = librosa.feature.spectral_centroid(y=segment, sr=sr)
    return float(np.mean(c))


def spectral_slope(segment: np.ndarray, sr: int = 22050) -> float:
    """Slope of log-magnitude spectrum. More negative = faster high-freq rolloff."""
    fft = np.fft.rfft(segment)
    mag = np.log(np.abs(fft) + 1e-10)
    freqs = np.arange(len(mag))
    return float(np.polyfit(freqs, mag, 1)[0])


def rise_time(segment: np.ndarray, sr: int = 22050) -> float:
    """Time from start to peak amplitude in ms. Longer = slower expulsive force."""
    peak_idx = int(np.argmax(np.abs(segment)))
    return float((peak_idx / sr) * 1000.0)


def zero_crossing_rate(segment: np.ndarray) -> float:
    """Mean ZCR. Higher = more airflow turbulence."""
    return float(np.mean(librosa.feature.zero_crossing_rate(segment)))


def expulsive_duration(segment: np.ndarray, sr: int = 22050) -> float:
    """Time above 50% of peak amplitude in ms. Longer = more sustained expulsion."""
    peak_amp = np.max(np.abs(segment))
    n_above = int(np.sum(np.abs(segment) > 0.5 * peak_amp))
    return float((n_above / sr) * 1000.0)


def crest_factor(segment: np.ndarray) -> float:
    """
    Peak / RMS.
    Higher = more impulsive burst = healthy cough.
    PD coughs are softer and more gradual → lower crest factor.
    """
    peak = float(np.max(np.abs(segment)))
    rms = float(np.sqrt(np.mean(segment ** 2)))
    return peak / rms if rms > 0 else 1.0


def phase_power_ratio(segment: np.ndarray, sr: int = 22050) -> float:
    """
    Phase Power Ratio (PRE).
    Splits cough into 3 equal phases; normalises middle-phase FFT magnitude
    by first-phase total power; returns ratio of energy in [1kHz, 2.5kHz]
    to energy in [0, 750Hz] in the middle (expiratory) phase.
    Higher ratio = more high-frequency expiratory burst = healthy.
    PD: middle phase dominated by low-frequency, ratio closer to 0.
    """
    n = len(segment)
    phase_len = n // 3
    if phase_len < 16:
        return 0.0

    p1 = np.abs(np.fft.rfft(segment[:phase_len]))
    p2 = np.abs(np.fft.rfft(segment[phase_len : 2 * phase_len]))
    p2_norm = p2 / (np.sum(p1) + 1e-17)

    fbin = sr / (2.0 * phase_len + 1e-17)
    f750 = max(1, int(np.ceil(750.0 / fbin)))
    f1k = max(1, int(np.ceil(1000.0 / fbin)))
    f2k5 = min(int(np.ceil(2500.0 / fbin)), len(p2_norm))

    low = float(np.sum(p2_norm[:f750]))
    hi = float(np.sum(p2_norm[f1k:f2k5]))
    return hi / (low + 1e-17)


# ── Main extraction ────────────────────────────────────────────────────────

def extract_features(
    y: np.ndarray,
    cough_segments: list[tuple[int, int]],
    sr: int = 22050,
) -> dict:
    """
    Extract all features for every detected cough segment, average them.

    Returns:
        {"averaged": {feature: mean, feature_std: std, ...},
         "per_cough": [{feature: value, ...}, ...]}
    """
    if not cough_segments:
        return None

    features_list = []
    for start, end in cough_segments:
        raw = y[start:end]
        seg = _preprocess(raw, sr)

        features_list.append({
            "peak_to_decay_ratio": peak_to_decay_ratio(seg),
            "spectral_centroid":   spectral_centroid_feature(seg, sr),
            "spectral_slope":      spectral_slope(seg, sr),
            "rise_time":           rise_time(seg, sr),
            "zero_crossing_rate":  zero_crossing_rate(seg),
            "expulsive_duration":  expulsive_duration(seg, sr),
            "crest_factor":        crest_factor(seg),
            "phase_power_ratio":   phase_power_ratio(seg, sr),
        })

    averaged = {}
    for key in features_list[0]:
        vals = [f[key] for f in features_list]
        averaged[key] = float(np.mean(vals))
        averaged[f"{key}_std"] = float(np.std(vals))

    return {"averaged": averaged, "per_cough": features_list}
