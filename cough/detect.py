"""
Cough detection: isolates individual cough segments from raw audio.
Uses librosa RMS envelope + dynamic thresholding + duration filtering.
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
    merge_gap_ms: float = 60.0,
    threshold_multiplier: float = 3.0,
) -> list[tuple[int, int]]:
    """
    Detect cough segments in an audio file.

    Returns list of (start_sample, end_sample) tuples.
    """
    y, _ = librosa.load(audio_path, sr=sr)

    # RMS envelope: 20 ms frames, 5 ms hops → smooth power curve
    frame_length = int(sr * 0.020)
    hop_length = int(sr * 0.005)
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]

    # Smooth with median filter to suppress impulse noise
    rms_smooth = signal.medfilt(rms, kernel_size=5)

    # Dynamic threshold: multiplier × median of non-silent frames
    nonzero = rms_smooth[rms_smooth > 1e-6]
    baseline = float(np.median(nonzero)) if len(nonzero) > 0 else float(np.median(rms_smooth))
    threshold = threshold_multiplier * baseline

    # Map frame-level envelope back to sample-level using linear interpolation
    frame_times = np.arange(len(rms_smooth)) * hop_length
    sample_times = np.arange(len(y))
    envelope_full = np.interp(sample_times, frame_times, rms_smooth)

    # Find contiguous regions above threshold
    above = (envelope_full > threshold).astype(np.int8)
    changes = np.diff(above, prepend=0, append=0)
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]

    if len(starts) == 0:
        return []

    # Merge segments with a gap shorter than merge_gap_ms
    merge_gap_samples = int(sr * merge_gap_ms / 1000.0)
    merged_starts = [starts[0]]
    merged_ends = [ends[0]]
    for s, e in zip(starts[1:], ends[1:]):
        if s - merged_ends[-1] <= merge_gap_samples:
            merged_ends[-1] = e
        else:
            merged_starts.append(s)
            merged_ends.append(e)

    # Duration filter
    min_samples = int(sr * min_duration_ms / 1000.0)
    max_samples = int(sr * max_duration_ms / 1000.0)

    coughs = []
    for start, end in zip(merged_starts, merged_ends):
        duration = end - start
        if min_samples <= duration <= max_samples:
            coughs.append((int(start), int(end)))

    return coughs
