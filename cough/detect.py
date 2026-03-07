"""
Cough detection using a hysteresis comparator on the RMS envelope.
Algorithm adapted from Orlandic et al. (2020) — detect-segment-cough.

Key improvement over single-threshold: two thresholds (low + high) prevent
jittery start/stop when the cough briefly dips during expiration.
Adaptive baseline (median of non-silent frames) handles variable mic gain.
"""
from __future__ import annotations

import numpy as np
import librosa
from scipy import signal


def detect_coughs(
    audio_path: str,
    sr: int = 22050,
    min_duration_ms: float = 80.0,
    max_duration_ms: float = 900.0,
    padding_ms: float = 25.0,
    th_l_mult: float = 2.0,
    th_h_mult: float = 8.0,
    tolerance_ms: float = 10.0,
) -> list[tuple[int, int]]:
    """
    Detect cough segments in an audio file.

    Uses adaptive hysteresis:
      - th_l = th_l_mult × median RMS  (low threshold: cough may continue)
      - th_h = th_h_mult × median RMS  (high threshold: new cough starts here)
      - tolerance: cough ends only after tolerance_ms consecutive frames below th_l

    Returns list of (start_sample, end_sample) tuples.
    """
    y, _ = librosa.load(audio_path, sr=sr)

    # Smooth RMS envelope: 20 ms frames, 5 ms hops
    frame_length = int(sr * 0.020)
    hop_length = int(sr * 0.005)
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    rms_smooth = signal.medfilt(rms, kernel_size=5)

    # Adaptive thresholds: based on median of active (non-silent) frames
    nonzero = rms_smooth[rms_smooth > 1e-6]
    baseline = float(np.median(nonzero)) if len(nonzero) > 0 else float(np.median(rms_smooth))
    th_l = th_l_mult * baseline
    th_h = th_h_mult * baseline

    # Interpolate frame-level RMS back to sample-level
    frame_centers = np.arange(len(rms_smooth)) * hop_length
    envelope = np.interp(np.arange(len(y)), frame_centers, rms_smooth)

    # Hysteresis state machine (Orlandic et al. 2020)
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
