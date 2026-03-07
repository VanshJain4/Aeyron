"""
Cough detection + PD scoring from raw numpy audio.
Wraps the cough/ pipeline for live integration (no file I/O).
"""
from __future__ import annotations

import warnings
import numpy as np
import librosa
from scipy import signal

warnings.filterwarnings("ignore", message="n_fft=.*is too large")


# ── Cough detection (hysteresis comparator) ───────────────────────────────

def detect_coughs_from_array(
    y: np.ndarray,
    sr: int = 16000,
    min_duration_ms: float = 80.0,
    max_duration_ms: float = 900.0,
    padding_ms: float = 25.0,
    th_l_mult: float = 2.0,
    th_h_mult: float = 8.0,
    tolerance_ms: float = 10.0,
) -> list[tuple[int, int]]:
    """Detect cough segments from a numpy array. Returns (start, end) sample tuples."""
    frame_length = int(sr * 0.020)
    hop_length = int(sr * 0.005)
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    rms_smooth = signal.medfilt(rms, kernel_size=5)

    nonzero = rms_smooth[rms_smooth > 1e-6]
    baseline = float(np.median(nonzero)) if len(nonzero) > 0 else float(np.median(rms_smooth))
    th_l = th_l_mult * baseline
    th_h = th_h_mult * baseline

    frame_centers = np.arange(len(rms_smooth)) * hop_length
    envelope = np.interp(np.arange(len(y)), frame_centers, rms_smooth)

    padding = int(sr * padding_ms / 1000.0)
    min_samples = int(sr * min_duration_ms / 1000.0)
    max_samples = int(sr * max_duration_ms / 1000.0)
    tolerance = int(sr * tolerance_ms / 1000.0)

    segments: list[tuple[int, int]] = []
    in_cough = False
    cough_start = 0
    below_count = 0
    n = len(envelope)

    for i in range(n):
        val = envelope[i]
        if in_cough:
            if val < th_l:
                below_count += 1
                if below_count > tolerance:
                    end = min(i + padding, n)
                    in_cough = False
                    dur = end - cough_start
                    if min_samples <= dur <= max_samples:
                        segments.append((max(0, cough_start), end))
            elif i == n - 1:
                end = i
                in_cough = False
                dur = end - cough_start
                if min_samples <= dur <= max_samples:
                    segments.append((max(0, cough_start), end))
            else:
                below_count = 0
        else:
            if val > th_h:
                cough_start = max(0, i - padding)
                in_cough = True
                below_count = 0

    return segments


# ── Feature extraction (from cough/features.py, inlined for no cross-folder imports) ──

def _preprocess(segment: np.ndarray, sr: int) -> np.ndarray:
    from scipy.signal import butter, filtfilt
    seg = segment.astype(np.float64)
    peak = np.max(np.abs(seg))
    if peak > 0:
        seg = seg / peak
    nyq = sr / 2.0
    if 6000.0 < nyq:
        b, a = butter(4, 6000.0 / nyq, btype="lowpass")
        seg = filtfilt(b, a, seg)
    return seg.astype(np.float32)


def _spectral_centroid(seg: np.ndarray, sr: int) -> float:
    c = librosa.feature.spectral_centroid(y=seg, sr=sr)
    return float(np.mean(c))


def _zero_crossing_rate(seg: np.ndarray) -> float:
    return float(np.mean(librosa.feature.zero_crossing_rate(seg)))


def _crest_factor(seg: np.ndarray) -> float:
    peak = float(np.max(np.abs(seg)))
    rms = float(np.sqrt(np.mean(seg ** 2)))
    return peak / rms if rms > 0 else 1.0


def _rise_time(seg: np.ndarray, sr: int) -> float:
    peak_idx = int(np.argmax(np.abs(seg)))
    return float((peak_idx / sr) * 1000.0)


def _peak_to_decay_ratio(seg: np.ndarray) -> float:
    abs_seg = np.abs(seg)
    peak_idx = int(np.argmax(abs_seg))
    first = seg[: peak_idx + 1]
    second = seg[peak_idx + 1 :]
    if len(first) == 0 or len(second) == 0:
        return 1.0
    rms_f = np.sqrt(np.mean(first ** 2))
    rms_s = np.sqrt(np.mean(second ** 2))
    return float(rms_f / rms_s) if rms_s > 0 else 100.0


def _expulsive_duration(seg: np.ndarray, sr: int) -> float:
    peak_amp = np.max(np.abs(seg))
    n_above = int(np.sum(np.abs(seg) > 0.5 * peak_amp))
    return float((n_above / sr) * 1000.0)


def _phase_power_ratio(seg: np.ndarray, sr: int) -> float:
    n = len(seg)
    phase_len = n // 3
    if phase_len < 16:
        return 0.0
    p1 = np.abs(np.fft.rfft(seg[:phase_len]))
    p2 = np.abs(np.fft.rfft(seg[phase_len : 2 * phase_len]))
    p2_norm = p2 / (np.sum(p1) + 1e-17)
    fbin = sr / (2.0 * phase_len + 1e-17)
    f750 = max(1, int(np.ceil(750.0 / fbin)))
    f1k = max(1, int(np.ceil(1000.0 / fbin)))
    f2k5 = min(int(np.ceil(2500.0 / fbin)), len(p2_norm))
    low = float(np.sum(p2_norm[:f750]))
    hi = float(np.sum(p2_norm[f1k:f2k5]))
    return hi / (low + 1e-17)


def extract_cough_features(y: np.ndarray, segments: list[tuple[int, int]], sr: int = 16000) -> dict | None:
    """Extract features from cough segments and return averaged dict."""
    if not segments:
        return None
    feats_list = []
    for start, end in segments:
        raw = y[start:end]
        seg = _preprocess(raw, sr)
        feats_list.append({
            "spectral_centroid": _spectral_centroid(seg, sr),
            "zero_crossing_rate": _zero_crossing_rate(seg),
            "crest_factor": _crest_factor(seg),
            "phase_power_ratio": _phase_power_ratio(seg, sr),
            "rise_time": _rise_time(seg, sr),
            "peak_to_decay_ratio": _peak_to_decay_ratio(seg),
            "expulsive_duration": _expulsive_duration(seg, sr),
        })
    averaged = {}
    for key in feats_list[0]:
        vals = [f[key] for f in feats_list]
        averaged[key] = float(np.mean(vals))
    return averaged


# ── PD likelihood scoring (from cough/pd_classifier.py) ──────────────────

def _lin(x: float, lo: float, hi: float, invert: bool = False) -> float:
    if hi == lo:
        return 0.0
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return (1.0 - t) if invert else t


def cough_pd_likelihood(features: dict) -> tuple[float, str]:
    """
    PD likelihood from cough features.
    Returns (score 0-1, label).
    """
    centroid = float(features.get("spectral_centroid", 1200.0))
    c_score = _lin(centroid, lo=600.0, hi=1800.0, invert=True)

    zcr = float(features.get("zero_crossing_rate", 0.10))
    z_score = _lin(zcr, lo=0.04, hi=0.14, invert=True)

    cf = float(features.get("crest_factor", 4.0))
    cf_score = _lin(cf, lo=2.5, hi=6.5, invert=True)

    pre = float(features.get("phase_power_ratio", 0.5))
    pre_score = _lin(pre, lo=0.15, hi=0.7, invert=True)

    rt = float(features.get("rise_time", 80.0))
    r_score = _lin(rt, lo=50.0, hi=200.0, invert=False)

    pdr = float(features.get("peak_to_decay_ratio", 0.7))
    p_score = _lin(pdr, lo=0.45, hi=0.90, invert=True)

    ed = float(features.get("expulsive_duration", 20.0))
    e_score = _lin(ed, lo=8.0, hi=35.0, invert=True)

    pd_score = (
        0.22 * c_score + 0.20 * z_score + 0.18 * cf_score +
        0.15 * pre_score + 0.13 * r_score + 0.07 * p_score + 0.05 * e_score
    )
    pd_score = max(0.0, min(1.0, pd_score))

    if pd_score < 0.35:
        label = "LOW_RISK"
    elif pd_score < 0.60:
        label = "MODERATE_RISK"
    else:
        label = "HIGH_RISK"

    return round(pd_score, 4), label


def run_cough_pipeline(y: np.ndarray, sr: int = 16000) -> dict:
    """
    Full cough pipeline: detect → extract features → PD score.
    Returns dict with cough_count, pd_score, pd_label, features (or None if no coughs).
    """
    segments = detect_coughs_from_array(y, sr=sr)
    if not segments:
        return {"cough_count": 0, "pd_score": None, "pd_label": None, "features": None}
    feats = extract_cough_features(y, segments, sr=sr)
    if feats is None:
        return {"cough_count": len(segments), "pd_score": None, "pd_label": None, "features": None}
    pd_score, pd_label = cough_pd_likelihood(feats)
    return {
        "cough_count": len(segments),
        "pd_score": pd_score,
        "pd_label": pd_label,
        "features": feats,
    }
